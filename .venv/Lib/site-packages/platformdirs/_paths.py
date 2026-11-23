"""Validate POSIX directory paths before using them."""

from __future__ import annotations

__lazy_modules__ = [
    "collections",
    "pathlib",
]

import os
import stat
from collections import deque
from pathlib import Path

TYPE_CHECKING = False
if TYPE_CHECKING:
    from typing import Literal

    _Policy = Literal["user", "runtime", "config", "site", "site-lookup"]


def create_checked_directories(path: Path, *, private: bool, policy: _Policy) -> None:
    absolute = path.absolute()
    existing = absolute
    while not existing.is_dir():
        existing = existing.parent
    if policy == "site-lookup" and existing != absolute:
        policy = "site"
    if problem := directory_problem(existing, policy=policy):
        raise PermissionError(problem)
    if existing == absolute:
        return
    owners = {0} if policy == "site" else {0, _effective_uid()}
    writable = stat.S_IWOTH if policy == "user" else stat.S_IWGRP | stat.S_IWOTH
    mode = 0o700 if private else 0o777 & ~writable
    for component in absolute.relative_to(existing).parts:
        existing /= component
        existing.mkdir(mode=mode, exist_ok=True)
        info = os.lstat(existing)
        if info.st_uid not in owners:
            msg = f"{existing} is not a trusted directory"
            raise PermissionError(msg)
        _check_directory(existing, info, writable)


def directory_problem(path: Path, *, missing_ok: bool = False, policy: _Policy = "runtime") -> str | None:
    if os.name == "nt":
        return None
    try:
        _verify_path(path.absolute(), policy)
    except FileNotFoundError as error:
        return None if missing_ok else f"{error.filename} is missing"
    except PermissionError as error:
        return str(error)
    except OSError as error:
        return f"{error.filename} cannot be checked: {error.strerror}"
    return None


def _verify_path(path: Path, policy: _Policy) -> None:
    directory = Path(path.anchor)
    pending = deque(path.parts[1:])
    owners = {0}
    if policy not in {"site", "site-lookup"}:
        owners.add(_effective_uid())
    parent = os.lstat(directory)
    writable = stat.S_IWGRP | stat.S_IWOTH if policy == "runtime" else stat.S_IWOTH
    links = 0
    max_links = 40
    while pending:
        entry = directory / pending.popleft()
        info = os.lstat(entry)
        if info.st_uid not in owners and (
            policy in {"config", "runtime", "site"} or not _allows_foreign_owner(info, parent)
        ):
            msg = f"{entry}, owned by uid {info.st_uid}"
            raise PermissionError(msg)
        if stat.S_ISLNK(info.st_mode):
            links += 1
            if links > max_links:
                msg = f"{entry}, which has too many symbolic links"
                raise PermissionError(msg)
            target = entry.readlink()
            if target.is_absolute():
                directory = Path(target.anchor)
                parent = os.lstat(directory)
            pending.extendleft(reversed(target.parts[bool(target.anchor) :]))
            continue
        _check_directory(entry, info, writable)
        directory = entry
        parent = info


def _allows_foreign_owner(info: os.stat_result, parent: os.stat_result) -> bool:
    shared = stat.S_IWGRP | stat.S_IWOTH
    # The owner of a shared sticky directory can rename even the caller's entries.
    if stat.S_ISLNK(info.st_mode) or (info.st_mode & shared and info.st_mode & stat.S_ISVTX):
        return False
    return not parent.st_mode & shared or info.st_uid == parent.st_uid


def _effective_uid() -> int:
    if hasattr(os, "geteuid"):
        return os.geteuid()
    return getattr(os, "getuid")()  # ruff:ignore[get-attr-with-constant]  # POSIX fallback absent from Windows stubs


def _check_directory(path: Path, info: os.stat_result, writable: int) -> None:
    if not stat.S_ISDIR(info.st_mode):
        msg = f"{path}, which is not a directory"
        raise PermissionError(msg)
    if info.st_mode & writable and not info.st_mode & stat.S_ISVTX:
        msg = f"{path}, writable by another user"
        raise PermissionError(msg)


def make_directories(path: Path, *, private: bool) -> None:
    # Private creation applies the XDG mode to every new directory, including intermediate parents.
    mode = 0o700 if private else 0o777
    missing = []
    while True:
        try:
            path.mkdir(mode=mode, exist_ok=True)
        except FileNotFoundError:
            parent = path.parent
            if parent == path:  # A missing drive or share has no parent to create.
                raise
            missing.append(path)
            path = parent
        else:
            break
    for directory in reversed(missing):
        directory.mkdir(mode=mode, exist_ok=True)


__all__ = [
    "create_checked_directories",
    "directory_problem",
    "make_directories",
]
