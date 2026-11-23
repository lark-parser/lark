"""Unix runtime directory checks."""

from __future__ import annotations

__lazy_modules__ = [
    "pathlib",
    "warnings",
    f"{__spec__.parent}._paths",  # ty: ignore[missing-union-attribute]  # imported modules have a spec
    f"{__spec__.parent}.api",  # ty: ignore[missing-union-attribute]  # imported modules have a spec
]

import os
import stat
import sys
import warnings
from pathlib import Path

from ._paths import directory_problem
from .api import RuntimeDirWarning

TYPE_CHECKING = False
if TYPE_CHECKING:
    from typing import Final, Literal, NoReturn

    _ModeCheck = Literal["private", "legacy", "lookup", "repair"]

if sys.platform == "win32":

    def geteuid() -> NoReturn:
        msg = "should only be used on Unix"
        raise RuntimeError(msg)

else:
    try:
        from os import geteuid
    except ImportError:
        from os import getuid as geteuid


def runtime_base_problem(path: str, *, missing_ok: bool, mode_check: _ModeCheck = "private") -> str | None:
    return runtime_dir_problem(path, missing_ok=missing_ok, mode_check=mode_check) or runtime_dir_parent_problem(
        path, missing_ok=missing_ok
    )


def runtime_dir_problem(path: str, *, missing_ok: bool, mode_check: _ModeCheck = "private") -> str | None:
    # A missing path passes under missing_ok. A caller that creates or reads below it must check again.
    try:
        # A trailing / or /. makes lstat follow a final symlink, while Path drops it.
        info = os.lstat(str(Path(path)))
    except FileNotFoundError:
        return None if missing_ok else f"{path} is missing"
    except OSError as error:
        return f"{path} cannot be checked: {error.strerror}"
    mode = info.st_mode & 0o777
    checks = (
        (stat.S_ISLNK(info.st_mode), "is a symlink"),
        (not stat.S_ISDIR(info.st_mode), "is not a directory"),
        (info.st_uid != (uid := geteuid()), f"is owned by uid {info.st_uid}, not {uid}"),
        (mode_check == "lookup" and bool(mode & 0o002), f"has writable mode {mode:04o}"),
        (mode_check == "legacy" and bool(mode & 0o022), f"has writable mode {mode:04o}"),
        (mode_check == "private" and mode != RUNTIME_DIR_MODE, f"has mode {mode:04o}, not {RUNTIME_DIR_MODE:04o}"),
    )
    return next((f"{path} {problem}" for failed, problem in checks if failed), None)


def runtime_dir_parent_problem(path: str, *, missing_ok: bool) -> str | None:
    if problem := directory_problem(Path(path).parent, missing_ok=missing_ok):
        return f"{path} is below {problem}"
    return None


def warn_once(message: str) -> None:
    # Each read repeats the check, so a warning per read would flood long-running programs.
    if message not in _WARNED:
        _WARNED.add(message)
        warnings.warn(message, RuntimeDirWarning, stacklevel=3)


_WARNED: Final[set[str]] = set()
RUNTIME_DIR_MODE: Final[int] = 0o700


__all__ = [
    "RUNTIME_DIR_MODE",
    "geteuid",
    "runtime_base_problem",
    "runtime_dir_parent_problem",
    "runtime_dir_problem",
    "warn_once",
]
