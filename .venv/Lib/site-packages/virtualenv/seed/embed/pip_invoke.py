from __future__ import annotations

__lazy_modules__ = [
    "base64",
    "csv",
    "hashlib",
    "io",
    "logging",
    "pathlib",
    "shutil",
    "signal",
    "subprocess",
    "tempfile",
    "threading",
    "virtualenv.seed.wheels",
    "virtualenv.seed.wheels.acquire",
    "virtualenv.seed.wheels.util",
    "virtualenv.util.path",
    "virtualenv.util.subprocess",
    "zipfile",
    f"{__spec__.parent}.via_app_data.pip_install.base",  # ty: ignore[missing-union-attribute]  # spec exists
]

import csv
import hashlib
import io
import logging
import os
import signal
from base64 import urlsafe_b64encode
from contextlib import contextmanager
from pathlib import Path
from shutil import copyfile
from stat import S_IMODE, S_ISDIR, S_ISREG
from subprocess import Popen, TimeoutExpired
from tempfile import TemporaryDirectory
from threading import current_thread, main_thread
from typing import TYPE_CHECKING, Final
from zipfile import ZipFile

from virtualenv.seed.wheels import get_wheel, pip_wheel_env_run
from virtualenv.seed.wheels.acquire import PIP_RUN
from virtualenv.seed.wheels.util import Version
from virtualenv.util.path import write_file
from virtualenv.util.subprocess import LogCmd

from .base_embed import BaseEmbed
from .via_app_data.pip_install.base import EntryPointConfig, encodes_as_utf8, needs_shell_shebang, shell_shebang

if TYPE_CHECKING:
    from collections.abc import Generator
    from types import FrameType

    from virtualenv.config.cli.parser import VirtualEnvOptions
    from virtualenv.create.creator import Creator
    from virtualenv.seed.wheels.util import Wheel


class PipInvoke(BaseEmbed):
    """Seeder that installs the seed packages by running pip in a subprocess.

    :param options: the parsed options

    """

    def __init__(self, options: VirtualEnvOptions) -> None:
        super().__init__(options)
        self._wheels: list[Path] = []

    def run(self, creator: Creator) -> None:
        """Install the seed packages into the environment with pip, then rewrite the launchers on POSIX.

        :param creator: the creator of the environment

        """
        if not self.enabled:
            return
        for_py_version: Final[str] = creator.interpreter.version_release_str
        with self.get_pip_install_cmd(creator.exe, for_py_version) as cmd:
            record_names: Final[list[str]] = self._detach_links(creator)
            # pip runs under the interpreter of the environment, so it must be a pip that supports that version
            env = pip_wheel_env_run(self.extra_search_dir, self.app_data, self.env, for_py_version)
            # pip reads PIP_PYTHON before it applies --isolated.
            env = {key: value for key, value in env.items() if not key.upper().startswith("PIP_")}
            env["PIP_CONFIG_FILE"] = os.devnull
            self._execute(cmd, env)
        if os.name == "posix":
            self._rewrite_launchers(creator, record_names)

    @contextmanager
    def get_pip_install_cmd(self, exe: Path, for_py_version: str) -> Generator[list[str], None, None]:
        """Yield the pip command that installs the seed packages for the given interpreter version.

        :param exe: the Python executable of the environment
        :param for_py_version: the Python version to install for

        :raises RuntimeError: when no wheel is found for a distribution

        :yields: the pip command, as a list of arguments

        """
        self._wheels.clear()
        cmd: Final[list[str]] = [
            str(exe),
            "-c",
            PIP_RUN,
            "-q",
            "install",
            "--only-binary",
            ":all:",
            "--disable-pip-version-check",
            "--isolated",
            "--no-user",
            "--ignore-installed",
            "--no-index",
        ]
        # Only the selected archives may participate in pip's filename-based selection.
        with TemporaryDirectory(prefix="virtualenv-seed-") as folder:
            cmd.extend(["--find-links", folder])
            for dist, version in self.distribution_to_versions().items():
                wheel: Final[Wheel | None] = get_wheel(
                    distribution=dist,
                    version=version,
                    for_py_version=for_py_version,
                    search_dirs=self.extra_search_dir,
                    download=self.download,
                    app_data=self.app_data,
                    do_periodic_update=self.periodic_update,
                    env=self.env,
                )
                if wheel is None:
                    msg: Final[str] = f"could not get wheel for distribution {dist}"
                    raise RuntimeError(msg)
                self._wheels.append(wheel.path)
                copyfile(wheel.path, Path(folder) / wheel.name)
                cmd.append(Version.as_pip_req(dist, wheel.version))
            yield cmd

    def _detach_links(self, creator: Creator) -> list[str]:
        record_names: Final[list[str]] = []
        for wheel in self._wheels:
            with ZipFile(wheel) as archive:
                names: Final[list[str]] = archive.namelist()
                for root in {creator.purelib, creator.platlib}:
                    for name in {entry.partition("/")[0] for entry in names}:
                        if Path(name).name != name or name in {"", ".", ".."}:
                            msg: Final[str] = f"invalid seed wheel entry {name!r}"
                            raise RuntimeError(msg)
                        self._detach_tree(root / name)
                for name in names:
                    if name.endswith(".dist-info/entry_points.txt"):
                        self._detach_entry_points(creator, archive.read(name).decode("utf-8"))
                record_name = next(
                    (name for name in names if name.count("/") == 1 and name.endswith(".dist-info/RECORD")), None
                )
                if record_name is None:
                    msg: Final[str] = f"missing RECORD in seed wheel {wheel}"
                    raise RuntimeError(msg)
                record_names.append(record_name)

        self._detach_metadata(creator)
        return record_names

    @staticmethod
    def _detach_tree(path: Path) -> None:
        if path.is_symlink():
            path.unlink()
        elif path.is_dir():
            if PipInvoke._redirects_directory(path.lstat()):
                path.rmdir()
                return
            for root, dirs, files in os.walk(path, onerror=PipInvoke._raise_walk_error, followlinks=False):
                for name in [*dirs, *files]:
                    PipInvoke._detach_entry(Path(root) / name, dirs)

    @staticmethod
    def _redirects_directory(info: os.stat_result) -> bool:
        # Windows sets the name surrogate bit on tags that redirect pathname lookup.
        return os.name == "nt" and S_ISDIR(info.st_mode) and bool(info.st_reparse_tag & 0x20000000)

    @staticmethod
    def _raise_walk_error(error: OSError) -> None:
        raise error

    @staticmethod
    def _detach_entry(entry: Path, dirs: list[str]) -> None:
        info: Final[os.stat_result] = entry.lstat()
        if PipInvoke._redirects_directory(info):
            entry.rmdir()
            dirs.remove(entry.name)
        elif not S_ISDIR(info.st_mode) and (not S_ISREG(info.st_mode) or info.st_nlink > 1):
            entry.unlink()
            if entry.name in dirs:
                dirs.remove(entry.name)

    def _detach_entry_points(self, creator: Creator, content: str) -> None:
        entries: Final[EntryPointConfig] = EntryPointConfig(interpolation=None, strict=False)
        entries.read_string(content)
        for section in ("console_scripts", "gui_scripts"):
            if entries.has_section(section):
                for script in entries[section]:
                    self._detach_script(creator, script)

    @staticmethod
    def _detach_script(creator: Creator, name: str) -> None:
        if Path(name).name != name or name in {"", ".", ".."}:
            msg: Final[str] = f"invalid seed wheel script {name!r}"
            raise RuntimeError(msg)
        scripts: Final[set[str]] = {name}
        if name == "pip" or (name.startswith("pip") and name[3:4].isdigit()):
            scripts.update({
                "pip",
                f"pip{creator.interpreter.version_info.major}",
                f"pip{creator.interpreter.version_info.major}.{creator.interpreter.version_info.minor}",
            })
        for script in scripts:
            for suffix in (".exe", "-script.py", "-script.pyw") if os.name == "nt" else ("",):
                if (path := creator.script_dir / f"{script}{suffix}").is_symlink():
                    path.unlink()

    def _detach_metadata(self, creator: Creator) -> None:
        for root in {creator.purelib, creator.platlib}:
            for distribution in self.distribution_to_versions():
                for entry in root.glob(f"{distribution.replace('-', '_')}-*"):
                    if entry.suffix in {".dist-info", ".virtualenv"} and entry.is_symlink():
                        entry.unlink()

    @staticmethod
    def _execute(cmd: list[str], env: dict[str, str]) -> None:
        logging.getLogger(__name__).debug("pip seed by running: %s", LogCmd(cmd, env))
        with PipInvoke._capture_sigint() as interrupts:
            process: Final[Popen[bytes]] = Popen(cmd, env=env)
            try:
                PipInvoke._wait_for_pip(process, interrupts)
            except BaseException:
                PipInvoke._terminate_pip(process)
                raise
            if process.returncode != 0:
                msg: Final[str] = f"failed seed with code {process.returncode}"
                raise RuntimeError(msg)

    @staticmethod
    @contextmanager
    def _capture_sigint() -> Generator[list[BaseException] | None, None, None]:
        handler = signal.getsignal(signal.SIGINT) if current_thread() is main_thread() else None
        if not callable(handler):
            yield None
            return

        interrupts: list[BaseException] = []

        def on_sigint(signum: int, frame: FrameType | None) -> None:
            if not interrupts:
                try:
                    handler(signum, frame)
                except BaseException as error:  # ruff:ignore[blind-except]  # preserve the caller's signal error
                    interrupts.append(error)

        signal.signal(signal.SIGINT, on_sigint)
        try:
            yield interrupts
        finally:
            if signal.getsignal(signal.SIGINT) is on_sigint:
                signal.signal(signal.SIGINT, handler)
            if interrupts:
                raise interrupts[0]

    @staticmethod
    def _wait_for_pip(process: Popen[bytes], interrupts: list[BaseException] | None) -> None:
        if interrupts is None:
            process.communicate()
            return
        while True:
            finished = PipInvoke._communicate_once(process)
            if interrupts:
                raise interrupts[0]
            if finished:
                break

    @staticmethod
    def _communicate_once(process: Popen[bytes]) -> bool:
        try:
            process.communicate(timeout=0.1)
        except TimeoutExpired:
            return False
        return True

    @staticmethod
    def _terminate_pip(process: Popen[bytes]) -> None:
        if process.poll() is None:
            process.kill()
            process.wait()

    def _rewrite_launchers(self, creator: Creator, record_names: list[str]) -> None:
        for record_name in record_names:
            for root in {creator.purelib, creator.platlib}:
                record: Final[Path] = root / record_name
                if record.is_file():
                    self._rewrite_record_launchers(record, root, creator)

    @staticmethod
    def _rewrite_record_launchers(record: Path, root: Path, creator: Creator) -> None:
        rows: Final[list[list[str]]] = list(csv.reader(io.StringIO(record.read_text(encoding="utf-8"))))
        exe: Final[bytes] = str(creator.exe).encode("utf-8")
        # Match the complete header because the interpreter path may contain line feeds.
        headers: Final[list[bytes]] = [
            b"#!/bin/sh\n'''exec' " + quoted + b' "$0" "$@"\n' + b"' '''\n" for quoted in (exe, b'"' + exe + b'"')
        ]
        if needs_shell_shebang(str(creator.exe)) or not encodes_as_utf8(str(creator.exe)):
            headers.append(b"#!" + exe + b"\n")
        changed = False
        for row in rows:
            path: Final[Path] = Path(os.path.abspath(str(root / row[0])))
            if path.parent != creator.script_dir or not path.is_file():
                continue
            content = path.read_bytes()
            if (header := next((candidate for candidate in headers if content.startswith(candidate)), None)) is None:
                continue
            content = shell_shebang(str(creator.exe)) + content[len(header) :]
            mode: Final[int] = S_IMODE(path.stat().st_mode) & 0o755
            path.unlink()
            with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode), "wb") as stream:
                stream.write(content)
            row[1:] = [
                f"sha256={urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b'=').decode('ascii')}",
                str(len(content)),
            ]
            changed = True
        if changed:
            buffer: Final[io.StringIO] = io.StringIO()
            csv.writer(buffer).writerows(rows)
            write_file(record, buffer.getvalue().encode("utf-8"))


__all__ = [
    "PipInvoke",
]
