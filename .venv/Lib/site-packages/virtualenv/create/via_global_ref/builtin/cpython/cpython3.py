from __future__ import annotations

__lazy_modules__ = [
    "collections",
    "fnmatch",
    "logging",
    "operator",
    "pathlib",
    "virtualenv.create.via_global_ref.builtin.ref",
    "virtualenv.create.via_global_ref.store",
    "virtualenv.util.path",
]

import abc
import fnmatch
import logging
import os
from collections import deque
from operator import methodcaller as method
from pathlib import Path
from stat import S_ISLNK, S_ISVTX, S_IWGRP, S_IWOTH
from typing import TYPE_CHECKING

from virtualenv.create.describe import Python3Supports
from virtualenv.create.via_global_ref.builtin.ref import ExePathRefToDest, PathRefToDest, RefWhen
from virtualenv.create.via_global_ref.store import is_store_python
from virtualenv.util.path import copy as copy_path
from virtualenv.util.path import ensure_dir

from .common import CPython, CPythonPosix, CPythonWindows, is_mac_os_framework, is_macos_brew

if TYPE_CHECKING:
    from collections.abc import Generator

    from python_discovery import PythonInfo

    from virtualenv.create.via_global_ref.builtin.ref import PathRef
    from virtualenv.create.via_global_ref.builtin.via_global_self_do import BuiltinViaGlobalRefMeta
    from virtualenv.create.via_global_ref.venv import Venv


class CPython3(CPython, Python3Supports, abc.ABC):
    """CPython 3 or later."""


class CPython3Posix(CPythonPosix, CPython3):
    """CPython 3 on POSIX platforms."""

    @classmethod
    def can_describe(cls, interpreter: PythonInfo) -> bool:
        """Accept CPython 3 interpreters that are neither macOS framework nor Homebrew builds.

        :param interpreter: the host interpreter to check

        :returns: ``True`` if this creator can describe the interpreter

        """
        return (
            is_mac_os_framework(interpreter) is False
            and is_macos_brew(interpreter) is False
            and super().can_describe(interpreter)
        )

    @classmethod
    # yields PathRef, which the base's Generator[ExePathRefToDest] does not allow
    def sources(cls, interpreter: PythonInfo) -> Generator[PathRef]:  # ty: ignore[incompatible-method-override]
        """Yield the POSIX executables, plus the shared library when the interpreter links one.

        :param interpreter: the host interpreter to take the files from

        :yields: the references to the host files

        """
        yield from super().sources(interpreter)
        if shared_lib := cls._shared_libpython(interpreter):
            yield PathRefToDest(shared_lib, dest=cls._to_lib, when=RefWhen.COPY)

    @classmethod
    def _shared_libpython(cls, interpreter: PythonInfo) -> Path | None:
        if not interpreter.sysconfig_vars.get("Py_ENABLE_SHARED"):
            return None
        if not isinstance(instsoname := interpreter.sysconfig_vars.get("INSTSONAME"), str) or not instsoname:
            return None
        if not isinstance(libdir := interpreter.sysconfig_vars.get("LIBDIR"), str) or not libdir:
            return None
        if not (lib_path := Path(libdir) / instsoname).exists():
            return None
        return lib_path

    @classmethod
    def _to_lib(cls, creator: CPython3Posix, src: Path) -> Path:
        return creator.dest / "lib" / src.name

    def run(self) -> None:
        """Check copied interpreter search paths before clearing the destination."""
        if not self.symlinks:
            self._check_shared_libpython_search(self)
        super().run()

    @staticmethod
    def _check_shared_libpython_search(creator: CPython3Posix | Venv) -> None:
        interpreter = creator.interpreter
        # CPython 3.11+ searches above the loaded library for a stdlib zip before using pyvenv.cfg's home.
        if interpreter.version_info < (3, 11) or not interpreter.sysconfig_vars.get("Py_ENABLE_SHARED"):
            return
        zip_name = (
            f"python{interpreter.version_info.major}{interpreter.version_info.minor}"
            f"{'t' if interpreter.free_threaded else ''}.zip"
        )
        host_prefix = Path(interpreter.system_prefix).resolve()
        platlibdir = interpreter.sysconfig_vars.get("platlibdir")
        if not isinstance(platlibdir, str):
            platlibdir = Path(interpreter.system_stdlib).parent.name
        for ancestor in creator.dest.parents:
            if ancestor.resolve() == host_prefix:
                continue
            CPython3Posix._check_candidate_stdlib(ancestor / platlibdir, zip_name)

    @staticmethod
    def _check_candidate_stdlib(lib_dir: Path, zip_name: str) -> None:
        try:
            parent_stat = lib_dir.parent.stat()
        except FileNotFoundError:
            return
        try:
            entry_stat = lib_dir.lstat()
        except FileNotFoundError:
            entry_stat = None
        if CPython3Posix._can_replace_entry(parent_stat, entry_stat):
            logging.getLogger(__name__).warning(
                "another account can change the copied Python standard-library search path %s (parent mode %o); "
                "use --symlinks or choose a private parent directory",
                lib_dir,
                parent_stat.st_mode & 0o7777,
            )
        resolved = CPython3Posix._resolve_candidate_lib(lib_dir)
        if not resolved.is_dir():
            if entry_stat and S_ISLNK(entry_stat.st_mode):
                raise CPython3Posix._unsafe_search_path(lib_dir, entry_stat)
            return
        for depth, path in enumerate((resolved, *resolved.parents) if resolved != lib_dir else (lib_dir,)):
            path_stat = path.lstat()
            if path_stat.st_uid not in {os.geteuid(), 0} or (
                (path_stat.st_mode & S_IWOTH or CPython3Posix._shared_group_can_replace(path_stat))
                and (depth == 0 or not path_stat.st_mode & S_ISVTX)
            ):
                raise CPython3Posix._unsafe_search_path(path, path_stat)
        zip_path = lib_dir / zip_name
        if zip_path.is_file() or zip_path.is_symlink():
            raise CPython3Posix._unsafe_search_path(zip_path, zip_path.lstat())

    @staticmethod
    def _can_replace_entry(parent_stat: os.stat_result, entry_stat: os.stat_result | None) -> bool:
        # A sticky directory still lets others add a missing entry or replace an entry they own.
        return parent_stat.st_uid not in {os.geteuid(), 0} or (
            (bool(parent_stat.st_mode & S_IWOTH) or CPython3Posix._shared_group_can_replace(parent_stat))
            and (not parent_stat.st_mode & S_ISVTX or entry_stat is None or entry_stat.st_uid not in {os.geteuid(), 0})
        )

    @staticmethod
    def _resolve_candidate_lib(lib_dir: Path) -> Path:
        candidate = Path(lib_dir.anchor)
        remaining = deque(lib_dir.parts[1:])
        seen: set[Path] = set()
        while remaining:
            part = remaining.popleft()
            # Resolve each link before "..", matching filesystem lookup order.
            if part == "..":
                candidate = candidate.parent
                continue
            candidate /= part
            try:
                path_stat = candidate.lstat()
            except FileNotFoundError:
                return candidate.joinpath(*remaining)
            if not S_ISLNK(path_stat.st_mode):
                continue
            if candidate in seen:
                raise CPython3Posix._unsafe_search_path(candidate, path_stat)
            seen.add(candidate)
            if CPython3Posix._can_replace_entry(candidate.parent.stat(), path_stat):
                raise CPython3Posix._unsafe_search_path(candidate, path_stat)
            target = candidate.readlink()
            absolute_target = target.is_absolute()
            candidate = Path(target.anchor) if absolute_target else candidate.parent
            remaining = deque((*(target.parts[1:] if absolute_target else target.parts), *remaining))
        return candidate

    @staticmethod
    def _unsafe_search_path(path: Path, path_stat: os.stat_result) -> ValueError:
        return ValueError(
            f"copied Python library has an unsafe standard-library search path: {path} "
            f"(mode {path_stat.st_mode & 0o7777:o}); use --symlinks"
        )

    @staticmethod
    def _shared_group_can_replace(path_stat: os.stat_result) -> bool:
        if not path_stat.st_mode & S_IWGRP:
            return False
        if path_stat.st_gid != os.getegid():
            return True
        import grp  # ruff:ignore[import-outside-top-level]  # unavailable on Windows
        import pwd  # ruff:ignore[import-outside-top-level]  # unavailable on Windows

        try:
            user = pwd.getpwuid(os.geteuid()).pw_name
            group = grp.getgrgid(path_stat.st_gid)
        except KeyError:
            return True
        # Directory services often do not enumerate accounts, so only a group named after the user counts as private.
        return (
            group.gr_name != user
            or any(member != user for member in group.gr_mem)
            or any(account.pw_gid == path_stat.st_gid and account.pw_name != user for account in pwd.getpwall())
        )

    def install_venv_shared_libs(self, venv_creator: Venv) -> None:
        """Copy the shared ``libpython`` next to the environment when it does not link the host's copy.

        :param venv_creator: the ``venv`` creator that built the environment

        """
        if venv_creator.symlinks:
            return
        if not (shared_lib := self._shared_libpython(venv_creator.interpreter)):
            return
        dest = venv_creator.dest / "lib" / shared_lib.name
        ensure_dir(dest.parent)
        copy_path(shared_lib, dest)


class CPython3Windows(CPythonWindows, CPython3):
    """CPython 3 on Windows."""

    @classmethod
    # returns an optional meta, which the base setup_meta does not allow
    def setup_meta(cls, interpreter: PythonInfo) -> BuiltinViaGlobalRefMeta | None:  # ty: ignore[incompatible-method-override]
        """Return the metadata for CPython 3 on Windows, or ``None`` for Windows Store builds.

        :param interpreter: the host interpreter

        :returns: the metadata, or ``None`` when the interpreter is installed from the Windows Store

        """
        if is_store_python(interpreter):  # store python is not supported here
            return None
        return super().setup_meta(interpreter)

    @classmethod
    # yields PathRef, which the base's Generator[ExePathRefToDest] does not allow
    def sources(cls, interpreter: PythonInfo) -> Generator[PathRef]:  # ty: ignore[incompatible-method-override]
        """Yield the executables, plus the DLL, ``pyd`` and zip files unless a launcher shim is used.

        :param interpreter: the host interpreter to take the files from

        :yields: the references to the host files

        """
        yield from cls.executables(interpreter)
        if not cls.has_shim(interpreter):
            yield from cls.dll_and_pyd(interpreter)
            yield from cls.python_zip(interpreter)

    @classmethod
    def executables(cls, interpreter: PythonInfo) -> list[PathRef] | Generator[PathRef]:
        """Yield the executables, using the ``venvlauncher`` shims on Python 3.13 and later.

        :param interpreter: the host interpreter to take the files from

        :returns: the executable references, with the launcher in place of ``python.exe`` when present

        """
        sources = super().sources(interpreter)
        if interpreter.version_info >= (3, 13):
            host = cls.host_python(interpreter)
            t_suffix = "t" if interpreter.free_threaded else ""
            d_suffix = cls._debug_suffix(interpreter)
            updated_sources: list[PathRef] = []
            for ref in sources:
                if ref.base == "python.exe":
                    launcher_path = host.with_name(f"venvlauncher{t_suffix}{d_suffix}.exe")
                    if launcher_path.exists():
                        new_ref = ExePathRefToDest(
                            launcher_path, dest=ref.dest, targets=[ref.base, *ref.aliases], must=ref.must, when=ref.when
                        )
                        updated_sources.append(new_ref)
                        continue
                elif ref.src.name == "pythonw.exe":
                    w_launcher_path = ref.src.with_name(f"venvwlauncher{t_suffix}{d_suffix}.exe")
                    if w_launcher_path.exists():
                        new_ref = ExePathRefToDest(
                            w_launcher_path,
                            dest=ref.dest,
                            targets=[ref.base, *ref.aliases],
                            must=ref.must,
                            when=ref.when,
                        )
                        updated_sources.append(new_ref)
                        continue
                updated_sources.append(ref)
            return updated_sources
        return sources

    @classmethod
    def host_python(cls, interpreter: PythonInfo) -> Path:
        """The executable the environment copies, the launcher shim when one exists.

        :param interpreter: the host interpreter

        :returns: the path of the host executable

        """
        if cls.has_shim(interpreter):
            # starting with CPython 3.7 Windows ships with a venvlauncher.exe that avoids the need for dll/pyd copies
            # it also means the wrapper must be copied to avoid bugs such as https://bugs.python.org/issue42013
            return cls.shim(interpreter)  # ty: ignore[invalid-explicit-return]
        return super().host_python(interpreter)

    @classmethod
    def shim(cls, interpreter: PythonInfo) -> Path | None:
        """Find the ``venv`` launcher shim in the standard library of the interpreter.

        :param interpreter: the host interpreter

        :returns: the path of the shim, ``None`` when it does not exist

        """
        root = Path(interpreter.system_stdlib) / "venv" / "scripts" / "nt"
        d_suffix = cls._debug_suffix(interpreter)
        if interpreter.version_info >= (3, 13):
            # https://github.com/python/cpython/issues/112984
            t_suffix = "t" if interpreter.free_threaded else ""
            exe_name = f"venvlauncher{t_suffix}{d_suffix}.exe"
        else:
            exe_name = f"python{d_suffix}.exe"
        if (shim := root / exe_name).exists():
            return shim
        return None

    @classmethod
    def _debug_suffix(cls, interpreter: PythonInfo) -> str:
        return "_d" if getattr(interpreter, "debug_build", False) else ""

    @classmethod
    def has_shim(cls, interpreter: PythonInfo) -> bool:
        """Whether the interpreter ships a ``venv`` launcher shim.

        :param interpreter: the host interpreter

        :returns: ``True`` when the shim exists

        """
        return cls.shim(interpreter) is not None

    @classmethod
    def dll_and_pyd(cls, interpreter: PythonInfo) -> Generator[PathRefToDest]:
        """Yield the DLL and ``pyd`` files next to the host executable and in its ``DLLs`` folder.

        :param interpreter: the host interpreter to take the files from

        :yields: the references to the DLL and ``pyd`` files, skipping the pywin32 ones

        """
        folders = [Path(interpreter.system_exe).parent]

        # May be missing on some Python hosts.
        # See https://github.com/pypa/virtualenv/issues/2368
        dll_folder = Path(interpreter.system_prefix) / "DLLs"
        if dll_folder.is_dir():
            folders.append(dll_folder)

        for folder in folders:
            for file in folder.iterdir():
                if file.suffix in {".pyd", ".dll"}:
                    # Skip pywin32 DLLs to avoid conflicts with pywin32 installation
                    # pywin32 has its own post-install that places DLLs in site-packages/pywin32_system32
                    # See https://github.com/pypa/virtualenv/issues/2662
                    if cls._is_pywin32_dll(file.name):
                        continue
                    yield PathRefToDest(file, cls.to_bin)

    @classmethod
    def _is_pywin32_dll(cls, filename: str) -> bool:
        # Check if a DLL file belongs to pywin32.
        # pywin32 DLLs follow patterns like: pywintypes39.dll, pythoncom39.dll
        return filename.lower().startswith(("pywintypes", "pythoncom"))

    @classmethod
    def python_zip(cls, interpreter: PythonInfo) -> Generator[PathRefToDest]:
        """``python{VERSION}.zip`` holds the compiled ``*.pyc`` std lib packages.

        ``VERSION`` is the ``py_version_nodot`` var from the ``sysconfig`` module.

        See https://docs.python.org/3/using/windows.html#the-embeddable-package, ``discovery.py_info.PythonInfo`` class
        (interpreter), and ``python -m sysconfig`` output.

        The embeddable Python distribution for Windows includes ``python{VERSION}.zip`` and ``python{VERSION}._pth``
        files. User can move/rename the zip file and edit ``sys.path`` by editing the ``_pth`` file. Here the
        ``pattern`` is used only for the default zip file name.

        :param interpreter: the host interpreter whose zip file is looked up

        :yields: a reference to the zip file, when it exists beside the interpreter

        """
        matched_paths = map(Path, fnmatch.filter(interpreter.path, f"*python{interpreter.version_nodot}.zip"))
        if (path := next(filter(method("exists"), matched_paths), None)) is not None:
            yield PathRefToDest(path, cls.to_bin)


__all__ = [
    "CPython3",
    "CPython3Posix",
    "CPython3Windows",
]
