from __future__ import annotations

__lazy_modules__ = [
    "contextlib",
    "csv",
    "io",
    "itertools",
    "pathlib",
    "posixpath",
    "shlex",
    "tempfile",
    "virtualenv.util.path",
    "zipfile",
    f"{__spec__.parent}._safe_extract_zip",  # ty: ignore[missing-union-attribute]  # imported modules have a spec
]

import csv
import io
import logging
import os
import posixpath
import re
import shlex
import stat
import zipfile
from abc import ABC, abstractmethod
from configparser import ConfigParser
from contextlib import suppress
from itertools import chain
from pathlib import Path
from tempfile import mkdtemp
from typing import TYPE_CHECKING, Final

from distlib.scripts import ScriptMaker, enquote_executable

from virtualenv.util.path import make_tree_read_only, remove_file, safe_delete, safe_delete_read_only

from ._safe_extract_zip import extract_zip

if TYPE_CHECKING:
    from virtualenv.create.creator import Creator

LOGGER: Final[logging.Logger] = logging.getLogger(__name__)  # simplint: ignore[module-variable-prefix]  # existing name
# https://learn.microsoft.com/en-us/windows/win32/fileio/maximum-file-path-limitation
# the path length Windows stops at without long path support, counting the terminating null
_MAX_PATH: Final[int] = 260
# a directory has to leave room for an 8.3 file name inside it
_MAX_DIR_PATH: Final[int] = _MAX_PATH - 12


_MATCH_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"""
                        (?P<name>[^\W\d]\w*?)  # the script name, which starts with a letter
                        -?\d+(?:\.\d+)*        # an optional dash and the version
                        """,
    re.VERBOSE,
)


class PipInstall(ABC):
    """Install one seed package from a wheel into the environment, using a cached image of the wheel.

    :param wheel: the wheel to install
    :param creator: the creator of the environment
    :param image_folder: the folder holding the cached image of the wheel

    """

    def __init__(self, wheel: Path, creator: Creator, image_folder: Path) -> None:
        self._wheel = wheel
        self._creator = creator
        self._image_dir = image_folder

    def install(self, version_info: tuple[int, ...]) -> None:
        """Install the package, replacing any previous version and creating its console scripts.

        :param version_info: the version of the Python interpreter the package is installed for

        """
        dist_info: Final[Path] = self._find_dist_info(self._image_dir)
        self._uninstall_previous_version(dist_info)
        # sync image
        for filename in self._image_dir.iterdir():
            self._sync(filename, self._creator.purelib / filename.name)
        # generate console executables
        consoles = set()
        script_dir = self._creator.script_dir
        for name, module in self._read_console_scripts(dist_info).items():
            consoles.update(self._create_console_entry_point(name, module, script_dir, version_info))
        LOGGER.debug("generated console scripts %s", " ".join(i.name for i in consoles))

    @staticmethod
    def _find_dist_info(folder: Path) -> Path:
        files = []
        for filename in folder.iterdir():
            files.append(filename.name)
            if filename.suffix == ".dist-info":
                return filename
        msg = f"no .dist-info at {folder}, has {', '.join(files)}"
        raise RuntimeError(msg)

    def _uninstall_previous_version(self, dist_info: Path) -> None:
        dist_name = dist_info.stem.split("-")[0]
        in_folders = chain.from_iterable([i.iterdir() for i in (self._creator.purelib, self._creator.platlib)])
        paths = (p for p in in_folders if p.stem.split("-")[0] == dist_name and p.suffix == ".dist-info" and p.is_dir())
        if (existing_dist := next(paths, None)) is not None:
            self._uninstall_dist(existing_dist, self._creator.dest)

    @staticmethod
    def _uninstall_dist(dist: Path, env_dir: Path) -> None:
        dist_base: Final[Path] = dist.parent
        LOGGER.debug("uninstall existing distribution %s from %s", dist.stem, dist_base)

        top_level = PipInstall._read_regular_metadata(dist / "top_level.txt")
        paths = {dist.parent / name.strip() for name in top_level.splitlines()} if top_level is not None else set()
        paths.add(dist)

        lexical_root: Final[Path] = Path(os.path.abspath(env_dir))
        root: Final[Path] = env_dir.resolve()
        paths.update(PipInstall._record_paths(dist, base_dirs=paths.copy(), lexical_root=lexical_root))

        metadata_parents: Final[set[Path]] = set(dist.resolve().parents)
        for entry in sorted(paths):
            if not Path(os.path.abspath(entry)).is_relative_to(lexical_root):
                LOGGER.warning("skip removal of %s listed by %s: not inside environment %s", entry, dist.name, root)
                continue
            if not entry.exists() and not entry.is_symlink():
                continue
            linked: Final[bool] = entry.is_symlink()
            junction: Final[bool] = (
                os.name == "nt"
                and not linked
                and stat.S_ISDIR((info := entry.lstat()).st_mode)
                # Windows name-surrogate tags redirect lookup; cloud placeholders keep ordinary directory contents.
                and bool(info.st_reparse_tag & 0x2000_0000)
            )
            try:
                # Unlinking a final link leaves its target intact; parent links still affect containment.
                resolved: Final[Path] = (
                    entry.parent.resolve(strict=True) / entry.name if linked or junction else entry.resolve(strict=True)
                )
            except OSError as exception:
                LOGGER.warning("skip removal of %s listed by %s: cannot resolve it: %s", entry, dist.name, exception)
                continue
            if root not in resolved.parents or resolved in metadata_parents:
                LOGGER.warning(
                    "skip removal of %s listed by %s: not inside environment %s or a parent of the metadata",
                    entry,
                    dist.name,
                    root,
                )
            elif junction:
                resolved.rmdir()
            elif resolved.is_dir() and not linked:
                safe_delete(resolved)
            else:
                remove_file(resolved)
        # without top_level.txt, as in wheels pip itself installs, RECORD lists files only and their directories stay behind
        PipInstall._remove_emptied_folders(paths, dist_base)

    @staticmethod
    def _read_regular_metadata(path: Path) -> str | None:
        if not path.is_file():
            if path.exists():
                LOGGER.warning("skip reading %s: not a regular file", path)
            return None
        # The directory entry can change between is_file() and open().
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOCTTY", 0)
        with os.fdopen(os.open(path, flags), "rb") as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                LOGGER.warning("skip reading %s: not a regular file", path)
                return None
            return handle.read().decode("utf-8")

    @staticmethod
    def _record_paths(dist: Path, base_dirs: set[Path], lexical_root: Path) -> set[Path]:
        content = PipInstall._read_regular_metadata(dist / "RECORD")
        if content is None:
            return set()
        paths: Final[set[Path]] = set()
        for row in csv.reader(io.StringIO(content, newline="")):
            if not row:
                continue
            path = dist.parent / row[0]
            if not any(p in base_dirs for p in path.parents):
                paths.add(path)
                # bytecode written after the install, by a --no-compile install or an -O run, is not in RECORD
                if path.suffix == ".py" and Path(os.path.abspath(path)).is_relative_to(lexical_root):
                    paths.update(PipInstall._bytecode_of(path))
        return paths

    @staticmethod
    def _bytecode_of(source: Path) -> list[Path]:
        # a cache file is <stem>.<tag>.pyc or <stem>.<tag>.opt-<n>.pyc; foo.bar.<tag>.pyc is the bytecode of another
        # module, foo.bar.py, which may belong to another distribution
        cached: Final[re.Pattern[str]] = re.compile(rf"{re.escape(source.stem)}\.[^.]+(?:\.opt-\d+)?\.pyc")
        return [
            source.with_suffix(".pyc"),
            source.with_suffix(".pyo"),
            *(path for path in (source.parent / "__pycache__").glob("*.pyc") if cached.fullmatch(path.name)),
        ]

    @staticmethod
    def _remove_emptied_folders(paths: set[Path], dist_base: Path) -> None:
        base: Final[Path] = dist_base.resolve()
        folders: Final[set[Path]] = set()
        for entry in paths:
            folder = Path(os.path.normpath(entry)).parent
            if folder.is_relative_to(dist_base):
                while folder != dist_base and folder not in folders:
                    folders.add(folder)
                    folder = folder.parent
        for folder in sorted(folders, key=lambda path: len(path.parts), reverse=True):
            # a RECORD row can lead through a link, so only remove what still resolves inside the packages folder
            if (
                folder.is_dir()
                and not folder.is_symlink()
                and base in folder.resolve().parents
                and not any(folder.iterdir())
            ):
                folder.rmdir()

    @abstractmethod
    def _sync(self, src: Path, dst: Path) -> None:
        raise NotImplementedError

    @staticmethod
    def _read_console_scripts(dist_info: Path) -> dict[str, str]:
        scripts: Final[dict[str, str]] = {}
        entry_points = dist_info / "entry_points.txt"
        if entry_points.exists():
            parser = EntryPointConfig(interpolation=None, strict=False)
            with entry_points.open(encoding="utf-8") as file_handler:
                parser.read_file(file_handler)
            if "console_scripts" in parser.sections():
                for name, value in parser.items("console_scripts"):
                    # fold only a trailing version (pip3, pip-3.13), so python3-config and 2to3 keep their names
                    match = _MATCH_PATTERN.fullmatch(name)
                    scripts[match.group("name") if match else name] = value
        return scripts

    def _create_console_entry_point(
        self, name: str, value: str, to_folder: Path, version_info: tuple[int, ...]
    ) -> list[Path]:
        new_files = ScriptMakerCustom(to_folder, version_info, self._creator.exe, name).make(f"{name} = {value}")
        result = []
        result.extend(Path(i) for i in new_files)
        return result

    def build_image(self) -> None:
        """Extract the seed wheel into a staging directory, fix up its RECORD file, then move it into place.

        Each archive entry is validated before extraction so a tampered wheel cannot escape the image directory via an
        absolute path or ``..`` traversal. Later runs reuse any image directory they find, so it only appears once the
        image is complete: a build that fails part way, for example on a full disk or a path that is too long, removes
        its staging directory, and the next build removes one that a killed process left behind.

        :raises RuntimeError: if the wheel contains an entry that would land outside the image directory.

        """
        # beside the installer folder the staging path is exactly as long as the image path, so the Windows path length
        # limits hit the build the same way they would hit the image
        staging: Final[Path] = self._image_dir.parent.with_name(f"{self._image_dir.parent.name}-{self._image_dir.name}")
        if staging.exists():
            safe_delete_read_only(staging)
        self._image_dir.parent.mkdir(parents=True, exist_ok=True)
        staging.mkdir()
        with zipfile.ZipFile(str(self._wheel)) as zip_ref:
            try:
                folder: Final[Path] = self._short_path_if_needed(zip_ref, staging)
            except BaseException:
                safe_delete(staging)
                raise
            try:
                self._populate_image(zip_ref, folder)
                # keep the short path Windows may have switched to, the install reads through it
                built: Final[Path] = folder.parent / self._image_dir.parent.name / self._image_dir.name
                with suppress(FileNotFoundError):
                    built.rmdir()  # an empty image directory counts as missing, but blocks the rename on Windows
                os.replace(folder, built)
            except BaseException:
                safe_delete_read_only(folder)
                raise
            # built ends in two long names again, so the files may only fit under the short path of the image itself
            self._image_dir = self._short_path_if_needed(zip_ref, built)

    @staticmethod
    def _short_path_if_needed(zip_ref: zipfile.ZipFile, folder: Path) -> Path:
        if os.name != "nt":
            return folder
        names: Final[list[str]] = zip_ref.namelist()
        prefix: Final[int] = len(str(folder)) + 1  # the separator before each entry
        longest_file: Final[int] = prefix + max(len(i) for i in names)
        longest_dir: Final[int] = prefix + max(len(posixpath.dirname(i)) for i in names)
        if longest_file < _MAX_PATH and longest_dir < _MAX_DIR_PATH:
            return folder
        # deferred, only the path-length fallback needs the short-path helper
        from virtualenv.util.path import get_short_path_name  # ruff:ignore[import-outside-top-level]

        return Path(get_short_path_name(str(folder)))

    def _populate_image(self, zip_ref: zipfile.ZipFile, folder: Path) -> None:
        LOGGER.debug("build install image for %s to %s", self._wheel.name, folder)
        extract_zip(zip_ref, folder)
        dist_info: Final[Path] = self._find_dist_info(folder)
        self._fix_records(folder, dist_info, self._generate_new_files(folder, dist_info))
        # environments link into the image, so a later write through such a link must fail instead of changing it
        make_tree_read_only(folder)

    @abstractmethod
    def _fix_records(self, folder: Path, dist_info: Path, extra_record_data: set[Path]) -> None:
        raise NotImplementedError

    def _generate_new_files(self, folder: Path, dist_info: Path) -> set[Path]:
        new_files = set()
        installer = dist_info / "INSTALLER"
        installer.write_text("pip\n", encoding="utf-8")
        new_files.add(installer)
        # inject a no-op root element, as workaround for bug in https://github.com/pypa/pip/issues/7226
        marker = folder / f"{dist_info.stem}.virtualenv"
        marker.write_text("", encoding="utf-8")
        new_files.add(marker)
        to_folder: Final[Path] = Path(mkdtemp())
        try:
            rel = os.path.relpath(str(self._creator.script_dir), str(self._creator.purelib))
            version_info = self._creator.interpreter.version_info
            for name, module in self._read_console_scripts(dist_info).items():
                new_files.update(
                    Path(os.path.normpath(str(folder / rel / i.name)))
                    # version_info is a VersionInfo, which the helper types as a plain tuple
                    for i in self._create_console_entry_point(name, module, to_folder, version_info)  # ty: ignore[invalid-argument-type]
                )
        finally:
            safe_delete(to_folder)
        return new_files

    @staticmethod
    def _records_text(folder: Path, files: set[Path] | list[Path]) -> str:
        stream = io.StringIO(newline="")
        csv.writer(stream).writerows((os.path.relpath(str(rec), str(folder)), "", "") for rec in files)
        return stream.getvalue()

    def clear(self) -> None:
        """Remove the cached image of the wheel."""
        if self._image_dir.exists():
            safe_delete_read_only(self._image_dir)

    def has_image(self) -> bool:
        """Whether the cached image of the wheel exists and holds files.

        On Windows an image that is found is switched to its short path when its files do not fit under the long one, as
        a build does, so the install can read them.

        :returns: ``True`` when the image has content

        """
        if not (self._image_dir.exists() and any(self._image_dir.iterdir())):
            return False
        if os.name == "nt":
            with zipfile.ZipFile(str(self._wheel)) as zip_ref:
                self._image_dir = self._short_path_if_needed(zip_ref, self._image_dir)
        return True


class EntryPointConfig(ConfigParser):
    """Config parser that keeps the option names as written, without lower-casing them."""

    @staticmethod
    def optionxform(optionstr: str) -> str:
        """Keep the option name as written.

        :param optionstr: the option name

        :returns: the option name unchanged

        """
        return optionstr


class ScriptMakerCustom(ScriptMaker):  # simplint: ignore[unexported-public-name]  # existing name
    """Writes the entry point scripts of a distribution, replacing any existing file of the same name.

    :param target_dir: the directory the scripts are written to
    :param version_info: the interpreter version, with ``major`` and ``minor``
    :param executable: the interpreter the scripts run with
    :param name: the name of the script

    :var clobber: ``True`` so existing scripts are overwritten
    :var set_mode: ``True`` so the scripts are made executable
    :var variants: the script variants to write, inherited from ``ScriptMaker``

    """  # simplint: ignore[function-docstring]  # existing docs

    def __init__(self, target_dir: Path, version_info: tuple[int, ...], executable: Path, name: str) -> None:
        super().__init__(None, str(target_dir))
        self.clobber = True  # overwrite
        self.set_mode = True  # ensure they are executable
        self.executable = enquote_executable(str(executable))
        # callers pass a VersionInfo with .major and .minor, the parameter is typed as tuple
        self.version_info = version_info.major, version_info.minor  # ty: ignore[missing-attribute]
        self.variants = {"", "X", "X.Y"}
        self._name = name
        self._raw_executable = str(executable)

    def _build_shebang(self, executable: bytes, post_interp: bytes) -> bytes:
        shebang: Final[bytes] = super()._build_shebang(executable, post_interp)
        if os.name != "posix" or (
            len(shebang.split()) == 1
            and not needs_shell_shebang(self._raw_executable)
            and encodes_as_utf8(self._raw_executable)
        ):
            return shebang
        return shell_shebang(self._raw_executable, post_interp)

    def _write_script(
        self, names: set[str], shebang: bytes, script_bytes: bytes, filenames: list[str], ext: str
    ) -> None:
        names.add(f"{self._name}{self.version_info[0]}.{self.version_info[1]}")
        for name in names:
            # A separator can route the script through a linked directory.
            if Path(name).name != name or name in {"", ".", ".."}:
                msg: Final[str] = f"invalid seed wheel script {name!r}"
                raise RuntimeError(msg)
            path: Final[Path] = Path(self.target_dir) / (f"{name}.exe" if os.name == "nt" else name)
            if path.is_symlink():
                path.unlink()
        super()._write_script(names, shebang, script_bytes, filenames, ext)


def needs_shell_shebang(executable: str) -> bool:
    """Whether the interpreter path needs a shell wrapper.

    :param executable: the interpreter path written in the shebang

    :returns: whether the path contains whitespace, quotes, or backslashes

    """
    return any(character in executable for character in " \t\n\v\f\r'\"\\")


def encodes_as_utf8(path: str) -> bool:
    """Check whether a path has the same filesystem and UTF-8 bytes.

    :param path: the path to compare

    :returns: whether its filesystem bytes equal its UTF-8 bytes

    """
    try:
        return os.fsencode(path) == path.encode("utf-8")
    except UnicodeEncodeError:
        return False


def shell_shebang(executable: str, post_interp: bytes = b"") -> bytes:
    # The exec line is read by both sh and Python; double-quoted backslashes survive both readers.
    """Build a shebang that runs the executable through ``sh`` and then Python.

    :param executable: the executable to run
    :param post_interp: the bytes appended after the interpreter path

    :returns: the shebang and the wrapper lines, as bytes

    """
    if encodes_as_utf8(executable):
        quoted = shlex.quote(executable).replace("\\", "'\"\\\\\"'").encode("utf-8")
    else:
        # The shell must use filesystem bytes while Python reads this header as UTF-8.
        escaped: Final[bytes] = b"".join(f"\\{byte:03o}".encode("ascii") for byte in os.fsencode(executable))
        quoted = b"\"$(printf '" + escaped + b"')\""
    return b"#!/bin/sh\n'''exec' " + quoted + post_interp + b' "$0" "$@"\n' + b"' '''\n"


__all__ = [
    "EntryPointConfig",
    "PipInstall",
    "encodes_as_utf8",
    "needs_shell_shebang",
    "shell_shebang",
]
