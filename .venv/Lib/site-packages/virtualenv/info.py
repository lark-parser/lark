from __future__ import annotations

__lazy_modules__ = [
    "tempfile",
    "typing",
]

import logging
import os
import platform
import sys
import tempfile
from typing import Final

#: The name of the Python implementation, as ``platform`` reports it.
IMPLEMENTATION: Final[str] = platform.python_implementation()
#: Whether the interpreter is PyPy.
IS_PYPY: Final[bool] = IMPLEMENTATION == "PyPy"
#: Whether the interpreter is GraalPy.
IS_GRAALPY: Final[bool] = IMPLEMENTATION == "GraalVM"
#: Whether the interpreter is RustPython.
IS_RUSTPYTHON: Final[bool] = IMPLEMENTATION == "RustPython"
#: Whether the interpreter is CPython.
IS_CPYTHON: Final[bool] = IMPLEMENTATION == "CPython"
#: Whether the platform is Windows.
IS_WIN: Final[bool] = sys.platform == "win32"
#: Whether the platform is macOS on Apple silicon.
IS_MAC_ARM64: Final[bool] = sys.platform == "darwin" and platform.machine() == "arm64"
#: The directory holding the virtualenv package, or the zipapp archive file.
ROOT: Final[str] = os.path.realpath(os.path.join(os.path.abspath(__file__), os.path.pardir, os.path.pardir))
#: Whether virtualenv runs from a zipapp archive.
IS_ZIPAPP: Final[bool] = os.path.isfile(ROOT)
_CAN_SYMLINK = _FS_CASE_SENSITIVE = None
LOGGER: Final[logging.Logger] = logging.getLogger(__name__)  # simplint: ignore[module-variable-prefix]  # existing name


def fs_supports_symlink() -> bool:
    """Whether the file system supports symlinks, checked once per process.

    :returns: ``True`` when a symlink can be created

    """
    global _CAN_SYMLINK  # ruff:ignore[global-statement]  # a module-level cache, filled on first use

    if _CAN_SYMLINK is None:
        can = False
        if hasattr(os, "symlink"):
            # Creating a symlink can fail for a variety of reasons, indicating that the filesystem does not support it.
            # E.g. on Linux with a VFAT partition mounted.
            with tempfile.NamedTemporaryFile(prefix="TmP") as tmp_file:
                dest = os.path.join(os.path.dirname(tmp_file.name), f"{tmp_file.name}-{'b'}")
                try:
                    os.symlink(tmp_file.name, dest)
                    can = True
                except (OSError, NotImplementedError):
                    pass  # symlink is not supported
                finally:
                    if os.path.lexists(dest):
                        os.remove(dest)
            LOGGER.debug("symlink on filesystem does%s work", "" if can else " not")
        _CAN_SYMLINK = can
    return _CAN_SYMLINK


def fs_path_id(path: str) -> str:
    """Return the identifier used to compare paths, folded to lower case on case-insensitive file systems.

    :param path: the path to identify

    :returns: the path, or its case-folded form on case-insensitive file systems

    """
    return path.casefold() if fs_is_case_sensitive() else path


def fs_is_case_sensitive() -> bool:
    """Whether the file system distinguishes letter case, checked once per process.

    :returns: ``True`` when the file system is case-sensitive

    """
    global _FS_CASE_SENSITIVE  # ruff:ignore[global-statement]  # a module-level cache, filled on first use

    if _FS_CASE_SENSITIVE is None:
        with tempfile.NamedTemporaryFile(prefix="TmP") as tmp_file:
            _FS_CASE_SENSITIVE = not os.path.exists(tmp_file.name.lower())
            LOGGER.debug("filesystem is %scase-sensitive", "" if _FS_CASE_SENSITIVE else "not ")
    return _FS_CASE_SENSITIVE


__all__ = [
    "IS_CPYTHON",
    "IS_GRAALPY",
    "IS_MAC_ARM64",
    "IS_PYPY",
    "IS_RUSTPYTHON",
    "IS_WIN",
    "IS_ZIPAPP",
    "ROOT",
    "fs_is_case_sensitive",
    "fs_path_id",
    "fs_supports_symlink",
]
