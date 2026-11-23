"""Private hard links for SQLite lock databases and cleanup of abandoned links."""

from __future__ import annotations

__lazy_modules__ = [
    "collections",
    "contextlib",
    "filelock._filesystem",
    "filelock._identity",
    "hashlib",
    "secrets",
    "tempfile",
    "threading",
]

import hashlib
import os
import secrets
import sys
import tempfile
import threading
import time
from collections import OrderedDict
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final, TypeAlias

from filelock._core import ForkResettable, override
from filelock._identity import host_name, link_host, owner_is_stale, process_start_token

if sys.platform == "win32":  # pragma: win32 cover
    from filelock._filesystem import directory_is_private, identity_at, make_private_directory, pinned

if TYPE_CHECKING:
    from collections.abc import Generator
    from contextlib import ExitStack

DatabaseIdentity: TypeAlias = tuple[int, int]
_DIRECTORY_FLAGS: Final[int] = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
_SWEEP_BUDGET: Final[float] = 0.05
_LINK_PREFIX: Final[str] = ".filelock-"
_LINK_NAME: Final[str] = "lock.db"
_MAX_REMEMBERED_SWEEPS: Final[int] = 1024
_SweepKey: TypeAlias = tuple[Path, int, int, DatabaseIdentity, int]


class _LinkSweeps(ForkResettable):
    def __init__(self) -> None:
        self._gate = threading.Lock()
        self._retry_at: OrderedDict[_SweepKey, float] = OrderedDict()
        self._pending: OrderedDict[_SweepKey, Generator[None]] = OrderedDict()

    def sweep(self, parent: Path, identity: DatabaseIdentity, owner: int) -> None:  # pragma: needs posix-hard-link
        # Opening a database need not wait for another connection's cleanup.
        if not self._gate.acquire(blocking=False):
            return
        try:
            with suppress(OSError):
                directory = parent.stat()
                self._advance((parent, directory.st_dev, directory.st_ino, identity, owner))
        finally:
            self._gate.release()

    def _advance(self, key: _SweepKey) -> None:  # pragma: needs posix-hard-link
        now = time.monotonic()
        if key in self._retry_at:
            self._retry_at.move_to_end(key)
            if now < self._retry_at[key]:
                return
        elif len(self._retry_at) == _MAX_REMEMBERED_SWEEPS:
            oldest, _ = self._retry_at.popitem(last=False)
            with suppress(KeyError):
                self._pending.pop(oldest).close()
        parent, _, _, identity, owner = key
        scan = self._pending.pop(key, None) or self._scan(parent, identity, owner)
        self._retry_at[key] = now + 60
        try:
            for _ in scan:
                if time.monotonic() >= now + _SWEEP_BUDGET:
                    self._pending[key] = scan
                    # Each paused directory iterator owns a handle.
                    max_pending_scans: Final[int] = 16
                    if len(self._pending) > max_pending_scans:
                        self._pending.popitem(last=False)[1].close()
                    return
            self._retry_at[key] = float("inf")
        finally:
            if key not in self._pending:
                scan.close()

    @staticmethod
    def _scan(parent: Path, identity: DatabaseIdentity, owner: int) -> Generator[None]:  # pragma: needs posix-hard-link
        with os.scandir(parent) as entries:
            for entry in entries:
                if entry.name.startswith(_LINK_PREFIX) and entry.is_dir(follow_symlinks=False):
                    with suppress(OSError):
                        _remove_dead_links(parent / entry.name, identity, owner)
                yield

    @override
    def _reset_after_fork_in_child(self) -> None:  # pragma: forked child
        self._gate = threading.Lock()
        for scan in self._pending.values():
            scan.close()
        self._pending.clear()
        self._retry_at.clear()


LINK_SWEEPS: Final[_LinkSweeps] = _LinkSweeps()


@dataclass(frozen=True, slots=True, kw_only=True)
class LinkDirectory:  # pragma: needs posix-hard-link
    path: Path
    identity: DatabaseIdentity
    # A watcher on a replaced outer directory cannot discover the final component.
    name: str

    @property
    def database(self) -> Path:
        return self.path / self.name / _LINK_NAME


def link_beside(  # pragma: needs posix-hard-link
    database: str, identity: DatabaseIdentity, owner: int
) -> LinkDirectory:
    # The link and database must share a filesystem.
    parent: Final[Path] = Path(database).parent
    LINK_SWEEPS.sweep(parent, identity, owner)
    path: Final[Path] = Path(tempfile.mkdtemp(prefix=_link_prefix(), dir=parent))
    fd: Final[int] = os.open(path, _DIRECTORY_FLAGS)
    try:
        made: Final[os.stat_result] = os.fstat(fd)
        # A peer can replace the new directory before open.
        loose: Final[int] = made.st_mode & 0o077
        if made.st_uid != owner or (loose and os.listdir(fd)):  # ruff:ignore[os-listdir]  # pathlib cannot list a descriptor
            msg = f"link directory {os.fspath(path)!r} was replaced while opening"
            raise OSError(msg)
        # An inherited ACL can override the mode mkdtemp requested.
        if loose:
            _tighten_link_directory(fd, parent)
        outer: Final[str] = secrets.token_hex(8)
        inner = secrets.token_hex(8)
        link: Final[LinkDirectory] = LinkDirectory(
            path=path, identity=(made.st_dev, made.st_ino), name=f"{outer}/{inner}"
        )
        try:
            _make_private_link_directories(fd, outer, inner, parent)
            os.link(database, link.database, follow_symlinks=False)
            linked: Final[os.stat_result] = link.database.stat(follow_symlinks=False)
        except BaseException:
            remove_link_directory(link)
            raise
    finally:
        os.close(fd)
    if (linked.st_dev, linked.st_ino) != identity:
        remove_link_directory(link)
        msg = f"lock database changed while opening: {database!r}"
        raise OSError(msg)
    return link


def _tighten_link_directory(fd: int, parent: Path) -> None:  # pragma: needs posix-hard-link
    msg = (
        "link directory stays open to other accounts through an inherited ACL"
        f" that chmod 0700 cannot close; make {os.fspath(parent)!r} writable by its owner only"
    )
    try:
        os.fchmod(fd, 0o700)
    except PermissionError as exc:
        raise PermissionError(msg) from exc
    if os.fstat(fd).st_mode & 0o077:
        raise PermissionError(msg)


def _make_private_link_directories(
    parent_fd: int, outer: str, inner: str, parent: Path
) -> None:  # pragma: needs posix-hard-link
    os.mkdir(outer, 0o700, dir_fd=parent_fd)
    outer_fd = os.open(outer, _DIRECTORY_FLAGS, dir_fd=parent_fd)
    try:
        if os.fstat(outer_fd).st_mode & 0o077:
            _tighten_link_directory(outer_fd, parent)
        os.mkdir(inner, 0o700, dir_fd=outer_fd)
    finally:
        os.close(outer_fd)


def _remove_dead_links(path: Path, identity: DatabaseIdentity, owner: int) -> None:  # pragma: needs posix-hard-link
    if sys.platform == "win32":  # pragma: win32 cover
        _remove_dead_links_on_windows(path, identity)
        return
    # A shared parent can contain an unrelated directory renamed to a dead holder's name.
    fd: Final[int] = os.open(path, _DIRECTORY_FLAGS)
    try:
        # Only an owned directory can hold this account's link.
        if os.fstat(fd).st_uid != owner or not _owner_is_gone(path.name):
            return
        with os.scandir(fd) as entries:
            names = [entry.name for entry in entries]
        removed_link = _remove_dead_links_below(fd, identity, names, depth=2)
    finally:
        os.close(fd)
    if not names or removed_link:
        with suppress(OSError):
            path.rmdir()


def _remove_dead_links_below(  # pragma: needs posix-hard-link
    fd: int, identity: DatabaseIdentity, names: list[str], *, depth: int
) -> bool:
    removed_link = _unlink_link_to(identity, fd)
    hex_digits = "0123456789abcdef"
    for name in names:
        if len(name) != len(hex_digits) or any(character not in hex_digits for character in name):
            continue
        try:
            nested = os.open(name, _DIRECTORY_FLAGS, dir_fd=fd)
        except OSError:
            continue
        try:
            if depth == 1:
                removed_nested_link = _unlink_link_to(identity, nested)
            else:
                with os.scandir(nested) as entries:
                    children = [entry.name for entry in entries]
                removed_nested_link = _remove_dead_links_below(nested, identity, children, depth=depth - 1)
        finally:
            os.close(nested)
        if removed_nested_link:
            removed_link = True
            with suppress(OSError):
                os.rmdir(name, dir_fd=fd)
    return removed_link


def _unlink_link_to(identity: DatabaseIdentity, dir_fd: int) -> bool:  # pragma: needs posix-hard-link
    try:
        linked: Final[os.stat_result] = os.stat(_LINK_NAME, dir_fd=dir_fd, follow_symlinks=False)
    except OSError:
        return False
    if (linked.st_dev, linked.st_ino) == identity:
        os.unlink(_LINK_NAME, dir_fd=dir_fd)
        return True
    return False


def _owner_is_gone(name: str) -> bool:  # pragma: needs posix-hard-link
    match name.removeprefix(_LINK_PREFIX).split("-"):
        case [pid, start, digest, _] if (
            pid.isascii() and pid.isdigit() and (not start or (start.isascii() and start.isdigit()))
        ):
            if not 1 <= (owner_pid := int(pid)) <= 2**31 - 1:
                return False
            return (
                (host := link_host()) is not None
                and digest == _host_digest(host)
                and owner_is_stale(owner_pid, host, int(start) if start else None)
            )
        case _:
            return False


def _link_prefix() -> str:  # pragma: needs posix-hard-link
    # Including the owner in the name lets a sweep identify a directory even if creation is interrupted.
    start: Final[int | None] = process_start_token(pid := os.getpid())
    host = link_host() or f"{host_name()}?pidns-unknown"
    return f"{_LINK_PREFIX}{pid}-{'' if start is None else start}-{_host_digest(host)}-"


def _host_digest(host: str) -> str:  # pragma: needs posix-hard-link
    # GraalPy lacks BLAKE2 with a custom digest size.
    return hashlib.sha256(host.encode()).hexdigest()[:16]


def remove_link_directory(link: LinkDirectory) -> None:  # pragma: needs posix-hard-link
    if sys.platform == "win32":  # pragma: win32 cover
        _remove_link_directory_on_windows(link)
        return
    # A peer can rename another directory onto the link path before cleanup.
    try:
        fd: Final[int] = os.open(link.path, _DIRECTORY_FLAGS)
    except OSError:
        return
    try:
        opened: Final[os.stat_result] = os.fstat(fd)
        if (opened.st_dev, opened.st_ino) != link.identity:
            return
        for suffix in ("", "-journal", "-wal", "-shm"):
            with suppress(FileNotFoundError):
                os.unlink(f"{link.name}/{_LINK_NAME}{suffix}", dir_fd=fd)
        for name in (link.name, link.name.partition("/")[0]):
            with suppress(FileNotFoundError):
                os.rmdir(name, dir_fd=fd)
    finally:
        os.close(fd)
    # A leftover empty directory does not affect the lock.
    with suppress(OSError):
        link.path.rmdir()


if sys.platform == "win32":  # pragma: win32 cover

    def link_beside_on_windows(database: str, identity: DatabaseIdentity, pin: ExitStack) -> LinkDirectory:
        parent: Final[Path] = Path(database).parent
        # Windows verifies ownership through the directory ACL.
        LINK_SWEEPS.sweep(parent, identity, 0)
        path: Final[Path] = parent / f"{_link_prefix()}{secrets.token_hex(8)}"
        make_private_directory(os.fspath(path))
        link: LinkDirectory | None = None
        try:
            # Keep the alias name bound until SQLite opens its database handle.
            link = LinkDirectory(
                path=path, identity=pin.enter_context(pinned(os.fspath(path))), name=secrets.token_hex(8)
            )
            _fill_link_directory(link, database, identity)
        except BaseException:
            pin.close()
            if link is not None:  # pragma: no branch  # a pinned directory always gets its link
                remove_link_directory(link)
            raise
        return link

    def _fill_link_directory(link: LinkDirectory, database: str, identity: DatabaseIdentity) -> None:
        if not directory_is_private(os.fspath(link.path)):
            msg = f"link directory {os.fspath(link.path)!r} was replaced while opening"
            raise OSError(msg)
        make_private_directory(os.fspath(link.path / link.name))
        os.link(database, link.database)
        # The open database handle prevents renames until its identity is verified.
        if identity_at(os.fspath(link.database)) != identity:
            msg = f"lock database changed while opening: {database!r}"
            raise OSError(msg)

    def _remove_dead_links_on_windows(path: Path, identity: DatabaseIdentity) -> None:
        with pinned(os.fspath(path)):
            if not directory_is_private(os.fspath(path)) or not _owner_is_gone(path.name):
                return
            with os.scandir(path) as entries:
                nested = [Path(entry.path) for entry in entries]
            for directory in nested:
                link = directory / _LINK_NAME
                with suppress(OSError):
                    if identity_at(os.fspath(link)) == identity:
                        link.unlink()
                with suppress(OSError):
                    directory.rmdir()
        with suppress(OSError):
            path.rmdir()

    def _remove_link_directory_on_windows(link: LinkDirectory) -> None:
        # A scanner may still hold the name. A later sweep retries cleanup.
        with suppress(OSError):
            with pinned(os.fspath(link.path)) as directory_identity:
                if directory_identity != link.identity:
                    return
                for suffix in ("", "-journal", "-wal", "-shm"):
                    with suppress(FileNotFoundError):
                        Path(f"{link.database}{suffix}").unlink()
                with suppress(FileNotFoundError):
                    link.database.parent.rmdir()
            link.path.rmdir()


__all__ = [
    "LINK_SWEEPS",
    "DatabaseIdentity",
    "LinkDirectory",
    "link_beside",
    "link_beside_on_windows",
    "remove_link_directory",
]
