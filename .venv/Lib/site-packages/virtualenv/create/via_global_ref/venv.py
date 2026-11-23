from __future__ import annotations

__lazy_modules__ = [
    "argparse",
    "pathlib",
    "python_discovery",
    "uuid",
    "virtualenv.util.error",
    "virtualenv.util.path",
    "virtualenv.util.subprocess",
    "virtualenv.util.text",
    f"{__spec__.parent}._venv_scripts",  # ty: ignore[missing-union-attribute]  # imported modules have a spec
    f"{__spec__.parent}.builtin.cpython.common",  # ty: ignore[missing-union-attribute]  # imported modules have a spec
    f"{__spec__.parent}.builtin.cpython.cpython3",  # ty: ignore[missing-union-attribute]  # imported modules have a spec
    f"{__spec__.parent}.builtin.cpython.mac_os",  # ty: ignore[missing-union-attribute]  # imported modules have a spec
    f"{__spec__.parent}.store",  # ty: ignore[missing-union-attribute]  # imported modules have a spec
    f"{__spec__.parent}.venv_copied",  # ty: ignore[missing-union-attribute]  # imported modules have a spec
]

import logging
import os
from argparse import ArgumentTypeError
from pathlib import Path
from stat import S_IMODE, S_IRGRP, S_IROTH, S_IRWXG, S_IRWXO, S_IXGRP, S_IXOTH
from typing import TYPE_CHECKING, Final
from uuid import uuid4

from python_discovery import PythonInfo

from virtualenv.util.error import ProcessCallFailedError
from virtualenv.util.path import ensure_within, remove_file
from virtualenv.util.subprocess import run_cmd
from virtualenv.util.text import collapse_line_boundaries

from ._venv_scripts import discard_stdlib_scripts, vendor_templates
from .api import ViaGlobalRefApi, ViaGlobalRefMeta
from .builtin.cpython.common import is_mac_os_framework
from .builtin.cpython.cpython3 import CPython3Posix
from .builtin.cpython.mac_os import CPython3macOsBrew
from .store import handle_store_python
from .venv_copied import remove_copied_interpreters

if TYPE_CHECKING:
    from virtualenv.config.cli.parser import VirtualEnvOptions

LOGGER: Final[logging.Logger] = logging.getLogger(__name__)  # simplint: ignore[module-variable-prefix]  # existing name


class Venv(ViaGlobalRefApi):
    """Create an environment with the stdlib ``venv`` module of the host interpreter.

    Runs inline when the host is the current interpreter, otherwise through a subprocess.

    :param options: the parsed command line options
    :param interpreter: the interpreter the environment is created from

    :var describe: the describer whose attributes stand in for the host interpreter, ``None`` when not describing
    :var can_be_inline: ``True`` when the host is the current interpreter and can create the environment in process

    """

    def __init__(self, options: VirtualEnvOptions, interpreter: PythonInfo) -> None:
        self.describe = options.describe
        super().__init__(options, interpreter)
        current = PythonInfo.current()
        self.can_be_inline = interpreter is current and interpreter.executable == interpreter.system_executable
        self._context = None

    def __getattribute__(
        self, item: str
    ) -> object:  # simplint: ignore[imprecise-annotation]  # proxied attributes differ in type
        if (describe := object.__getattribute__(self, "describe")) is not None and hasattr(describe, item):
            element = getattr(describe, item)
            if not callable(element) or item == "script":
                return element
        return object.__getattribute__(self, item)

    def _args(self) -> list[tuple[str, str | bool]]:
        return super()._args() + ([("describe", self.describe.__class__.__name__)] if self.describe else [])

    @classmethod
    def can_create(cls, interpreter: PythonInfo) -> ViaGlobalRefMeta | None:
        """Allow creation when ``venv`` is available, recording the store and framework limits.

        :param interpreter: the interpreter to check

        :returns: the capability metadata, or ``None`` when the interpreter has no ``venv`` module

        """
        if interpreter.has_venv:
            if CPython3macOsBrew.can_describe(interpreter):
                return CPython3macOsBrew.setup_meta(interpreter)
            meta = ViaGlobalRefMeta()
            if interpreter.platform == "win32":
                meta = handle_store_python(meta, interpreter)
            if is_mac_os_framework(interpreter):
                meta.copy_error = "macOS framework builds do not support copy-based virtual environments"
            return meta
        return None

    def create(self) -> None:
        """Create the environment, first checking the destination paths stay within it."""
        # stdlib venv writes interpreter files, configuration and activation scripts in place, so a planted symlink or
        # hard link would receive them outside the environment
        for directory in (
            self.bin_dir,
            self.purelib,
            self.platlib,
            self.dest / ("Include" if self.interpreter.os == "nt" else "include"),
        ):
            ensure_within(self.dest, directory)
        remove_copied_interpreters(self.bin_dir, self.interpreter)
        for path in (self.dest / "pyvenv.cfg", self.dest / ".gitignore", *self.bin_dir.iterdir()):
            if path.is_symlink() or (path.is_file() and path.stat().st_nlink > 1):
                path.unlink()
        if os.name == "posix":
            self._create_with_copy_mode()
        elif self.can_be_inline:
            self.create_inline()
        else:
            self.create_via_sub_process()
        discard_stdlib_scripts(self.bin_dir, remove_file)
        if self.describe is not None:
            self.describe.install_venv_shared_libs(self)
        super().create()

    def _create_with_copy_mode(self) -> None:
        # The empty probe receives file-only ACL entries and is unlinked before interpreter bytes are copied.
        probe = self.bin_dir / f".virtualenv-mode-{uuid4().hex}"
        # codeql[py/overly-permissive-file]  # ruff:ignore[commented-out-code]  # empty probe
        descriptor = os.open(probe, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o755)
        try:
            probe.unlink()
            allowed = S_IMODE(os.fstat(descriptor).st_mode) | 0o7000
        finally:
            os.close(descriptor)
        if not self.symlinks:
            # Only POSIX interpreter copies need the ACL check.
            from virtualenv.util.path import owner_executable_mode  # ruff:ignore[import-outside-top-level]

            allowed = owner_executable_mode(self.bin_dir, allowed)
        mode = S_IMODE(self.bin_dir.stat().st_mode)
        # stdlib chmods copies to 0755. Hide them from classes denied either read or execute until their mode is fixed.
        removed = 0
        if allowed & (S_IRGRP | S_IXGRP) != S_IRGRP | S_IXGRP and mode & S_IXGRP:
            removed |= mode & S_IRWXG
        if allowed & (S_IROTH | S_IXOTH) != S_IROTH | S_IXOTH and mode & S_IXOTH:
            removed |= mode & S_IRWXO
        kept = {path.name for path in self.bin_dir.iterdir()} - {Path(self.interpreter.system_exe).name}
        if removed:
            self.bin_dir.chmod(mode & ~removed)
        try:
            if self.can_be_inline:
                self.create_inline()
            else:
                self.create_via_sub_process()
        finally:
            try:
                for path in self.bin_dir.iterdir():
                    if path.name not in kept and path.is_file() and not path.is_symlink():
                        path.chmod(S_IMODE(path.stat().st_mode) & allowed)
            finally:
                if removed:
                    # A concurrent creator may have restored other bits.
                    self.bin_dir.chmod(S_IMODE(self.bin_dir.stat().st_mode) | removed)

    def create_inline(self) -> None:
        """Create the environment with the stdlib ``venv`` module imported in this process."""
        # Not every interpreter ships the stdlib venv module.
        from venv import EnvBuilder  # ruff:ignore[import-outside-top-level]

        class TemplateBuilder(EnvBuilder):
            install_scripts = vendor_templates(EnvBuilder.install_scripts)

        builder = TemplateBuilder(
            system_site_packages=self.enable_system_site_package,
            clear=False,
            symlinks=self.symlinks,
            with_pip=False,
        )
        builder.create(str(self.dest))

    def create_via_sub_process(self) -> None:
        """Create the environment with the stdlib ``venv`` module of the host interpreter in a subprocess.

        :raises ProcessCallFailedError: when the subprocess exits with a non-zero code

        """
        cmd = self.get_host_create_cmd()
        LOGGER.info("using host built-in venv to create via %s", " ".join(cmd))
        code, out, err = run_cmd(cmd, env={**self.env, "PYTHONSAFEPATH": "1"})
        if code != 0:
            raise ProcessCallFailedError(code, out, err, cmd)

    def get_host_create_cmd(self) -> list[str]:
        """Return the command that creates the environment with the host interpreter's ``venv`` module.

        :returns: the command line, as a list of arguments

        """
        cmd = [
            self.interpreter.system_executable,
            "-c",
            (
                "import sys; sys.path[:] = [p for p in sys.path if p != '']; "
                "import os, runpy, venv; sys.path.insert(0, os.path.dirname(sys.argv.pop(1))); "
                "from _venv_scripts import vendor_templates; sys.path.pop(0); "
                "venv.EnvBuilder.install_scripts = vendor_templates(venv.EnvBuilder.install_scripts); "
                "runpy.run_module('venv', run_name='__main__', alter_sys=True)"
            ),
            __file__,
            "--without-pip",
        ]
        if self.interpreter.version_info >= (3, 13):
            cmd.append("--without-scm-ignore-files")
        if self.enable_system_site_package:
            cmd.append("--system-site-packages")
        cmd.extend(("--symlinks" if self.symlinks else "--copies", str(self.dest)))
        # system_executable is optional in PythonInfo, so the command list is list[str | None]
        return cmd  # ty: ignore[invalid-explicit-return]

    @classmethod
    def validate_dest(cls, raw_value: str) -> str:
        """Validate the destination, rejecting line boundaries that the stdlib ``venv`` cannot record.

        :param raw_value: the destination as given on the command line

        :returns: the destination path as a string

        :raises ArgumentTypeError: when the destination contains a line boundary

        """
        return cls._check_line_boundaries(super().validate_dest(cls._check_line_boundaries(raw_value)))

    @staticmethod
    def _check_line_boundaries(value: str) -> str:
        # stdlib venv writes the destination into pyvenv.cfg without escaping line boundaries.
        if collapse_line_boundaries(value) != value:
            msg: Final[str] = (
                f"destination {value!r} must not contain a line boundary as venv cannot record it in pyvenv.cfg"
            )
            raise ArgumentTypeError(msg)
        return value

    def set_pyenv_cfg(self) -> None:
        """Record the GraalPy launcher settings in the ``pyvenv.cfg`` file."""
        super().set_pyenv_cfg()
        if self.interpreter.implementation == "GraalPy":
            # GraalPy launchers need these settings on Windows and macOS.
            self.pyenv_cfg["venvlauncher_command"] = self.interpreter.system_exe
            self.pyenv_cfg["base-executable"] = self.interpreter.system_exe

    def run(self) -> None:
        """Check copied interpreter search paths before clearing the destination."""
        if isinstance(self.describe, CPython3Posix) and not self.symlinks:
            CPython3Posix._check_shared_libpython_search(self)  # ruff:ignore[private-member-access]  # shared preflight
        previous = self.pyenv_cfg.content
        super().run()
        if os.name != "posix" or not previous:
            return
        recorded = previous.get("python-version") or previous.get("version_info") or previous.get("version") or ""
        version = ".".join(recorded.split(".")[:2])
        current = self.interpreter.version_info
        names: set[str] = set()
        if version and version != f"{current.major}.{current.minor}":
            names.update({f"python{version}", f"python{version}t"})
            if previous.get("implementation") == "CPython" and version == "3.14":
                names.add("𝜋thon")
        if previous.get("implementation") == "PyPy":
            if self.interpreter.implementation != "PyPy":
                names.update({"pypy", "pypy3"})
            if names:
                names.update({f"pypy{version}", f"libpypy{version}-c.so", f"libpypy{version}-c.dylib"})
        if names:
            remaining = sorted(path.name for path in self.bin_dir.iterdir() if path.name in names and path.is_file())
            if remaining:
                LOGGER.warning(
                    "files named for the previous interpreter remain in %r and may no longer work: %s. "
                    "Use a fresh destination to avoid stale files.",
                    os.fspath(self.bin_dir),
                    ", ".join(map(repr, remaining)),
                )


__all__ = [
    "Venv",
]
