"""SQLite lock database validation and connection ownership."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    assert __spec__ is not None

__lazy_modules__ = [
    "collections",
    "filelock._filesystem",
    "itertools",
    "pathlib",
    "threading",
    f"{__spec__.parent}._fork",
    f"{__spec__.parent}._links",
]

import os
import pathlib
import sqlite3
import stat
import sys
import threading
from collections import deque
from contextlib import ExitStack, contextmanager, suppress
from dataclasses import dataclass, field
from errno import EACCES
from itertools import count
from typing import TYPE_CHECKING, Final, TypeAlias

from filelock._core import (
    ForkResettable,
    fork_transition,
    override,
    register_owned_descriptor,
    unregister_owned_descriptor,
)
from filelock._filesystem import foreign_owner

from ._fork import FORKED_DATABASES, GETPID, sqlite_transition
from ._links import link_beside, remove_link_directory

if sys.platform == "win32":  # pragma: win32 cover
    from filelock._filesystem import directory_is_private, identity_of_fd, open_non_reparse_fd

    from ._links import link_beside_on_windows

if TYPE_CHECKING:
    from collections.abc import Callable, Generator
    from typing import Self

    from ._links import DatabaseIdentity, LinkDirectory


_ConnectionParameter: TypeAlias = (
    str | bytes | os.PathLike[str] | os.PathLike[bytes] | float | int | type[sqlite3.Connection] | None
)


def connect(database: str, *, factory: type[ForkSafeConnection], timeout: float) -> ForkSafeConnection:
    FORKED_DATABASES.note_sqlite_use()
    if sys.platform == "win32":  # pragma: win32 cover
        fd = _open_lock_database(database)
        link: LinkDirectory | None = None
        try:
            _raise_if_unsupported_sqlite_format(fd, database)
            target = database
            try:
                with ExitStack() as pin:
                    if not directory_is_private(os.fspath(pathlib.Path(database).parent)) or _side_file_exists(
                        database
                    ):
                        link = link_beside_on_windows(database, identity_of_fd(fd), pin)
                        target = os.fspath(link.database)
                    connection = sqlite3.connect(
                        target, check_same_thread=False, factory=factory, cached_statements=0, timeout=timeout
                    )
            except BaseException:
                if link is not None:
                    remove_link_directory(link)
                raise
            connection.retain_link(link)
            return connection
        finally:
            os.close(fd)
    return _connect_through_descriptor(  # pragma: win32 no cover
        database, factory=factory, timeout=timeout, owner=os.geteuid()
    )


def _open_lock_database(database: str) -> int:
    if sys.platform == "win32":  # pragma: win32 cover
        # Deny delete sharing so the database name stays pinned until SQLite opens it.
        if (fd := open_non_reparse_fd(database, 0o600)) is None:
            msg = f"lock database {database!r} is held without sharing or pending deletion"
            raise PermissionError(msg)
        return fd
    # O_NONBLOCK lets the regular-file check reject a FIFO without waiting for a writer.
    flags = (
        os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    )  # pragma: win32 no cover
    fd = os.open(database, flags, 0o600)  # pragma: win32 no cover
    if not stat.S_ISREG(os.fstat(fd).st_mode):  # pragma: win32 no cover
        os.close(fd)
        msg = f"refusing a non-regular lock database: {database!r}"
        raise OSError(msg)
    return fd  # pragma: win32 no cover


def _raise_if_unsupported_sqlite_format(fd: int, database: str) -> None:
    # A reused probe can share its file offset with another connection.
    header: Final[bytes] = os.pread(fd, 20, 0) if hasattr(os, "pread") else os.read(fd, 20)
    # WAL admits concurrent readers, and newer write formats can silently open read-only.
    if header.startswith(b"SQLite format 3\x00"):
        versions = header[18:20]
        wal_format_version: Final[int] = 2
        if wal_format_version in versions:
            msg = f"refusing a WAL-mode lock database: {database!r}; give ReadWriteLock a file of its own"
            raise ValueError(msg)
        if versions != b"\x01\x01":
            msg = f"refusing a lock database with unsupported SQLite format versions: {database!r}"
            raise ValueError(msg)


def _side_file_exists(database: str) -> bool:
    return any(os.path.lexists(f"{database}{suffix}") for suffix in ("-journal", "-wal", "-shm"))


def _connect_through_descriptor(  # pragma: win32 no cover
    database: str, *, factory: type[ForkSafeConnection], timeout: float, owner: int
) -> ForkSafeConnection:
    # Record each probe before taking its lease so an interrupt can release it.
    claimed: Final[list[_Probe]] = []
    link: LinkDirectory | None = None
    try:
        if (probe := PROBE_DESCRIPTORS.adopt(database, claimed)) is None:
            probe = PROBE_DESCRIPTORS.retain(_open_lock_database(database), claimed)
        # A reused probe may now be reached through a sticky directory owned by another account.
        foreign: Final[int | None] = foreign_owner(os.fstat(probe.fd), pathlib.Path(database).parent.stat())
        if foreign is not None:  # pragma: needs foreign-sticky-tmp
            reason = f"lock database belongs to uid {foreign}, not to this process's account or the directory's owner"
            raise PermissionError(EACCES, reason, database)
        # Finalizers can queue releases while the probe table is locked.
        PROBE_DESCRIPTORS.drain()
        _raise_if_unsupported_sqlite_format(probe.fd, database)
        target = database
        status: Final[os.stat_result] = os.lstat(pathlib.Path(database).parent)  # pragma: needs posix-hard-link
        # Other accounts can plant side files even in sticky directories.
        writable_by_others: Final[int] = status.st_mode & (stat.S_IWGRP | stat.S_IWOTH)  # pragma: needs posix-hard-link
        if (
            status.st_uid not in {owner, 0} or writable_by_others or _side_file_exists(database)
        ):  # pragma: needs posix-hard-link
            link = link_beside(database, probe.identity, owner)
            # A swept private link must not let SQLite create a new database outside the existing holder's lock.
            target = f"{link.database.as_uri()}?mode=rw"
        connection = sqlite3.connect(
            target,
            uri=link is not None,
            check_same_thread=False,
            factory=factory,
            cached_statements=0,
            timeout=timeout,
        )
        connection.retain_until_close(link, probe)
        claimed.clear()
        return connection
    finally:
        for unowned in claimed:
            PROBE_DESCRIPTORS.release(unowned)
        if claimed and link is not None:  # pragma: needs posix-hard-link
            remove_link_directory(link)


@contextmanager
def bounded_schema(connection: sqlite3.Connection, database: str) -> Generator[None]:
    # SQLite loads the whole schema before executing the first statement. A lock database needs none.
    calls: Final[count[int]] = count()
    max_calls: Final[int] = 10
    connection.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 1024)
    connection.set_progress_handler(lambda: next(calls) >= max_calls, 50)
    try:
        yield
    except sqlite3.DatabaseError as error:
        # An interrupted schema load reports a malformed schema rather than the interrupt.
        if isinstance(error, sqlite3.DataError) or next(calls) > max_calls:
            msg = (
                f"refusing a lock database whose schema is too large to load: {database!r}; "
                "give ReadWriteLock a file of its own"
            )
            raise ValueError(msg) from error
        raise
    finally:
        connection.set_progress_handler(None, 0)


class ForkSafeConnection(sqlite3.Connection):
    creator_pid: int | None
    _decrement_escrow: Callable[[sqlite3.Connection], None] | None
    _database_directory: LinkDirectory | None
    database_identity: DatabaseIdentity | None = None
    _probe: _Probe | None = None

    @override
    def __new__(
        cls,
        *_args: _ConnectionParameter,
        **_kwargs: _ConnectionParameter,
    ) -> Self:
        connection = super().__new__(cls)
        connection.creator_pid = GETPID()
        connection._decrement_escrow = None
        connection._database_directory = None
        return connection

    def __del__(
        self, _is_finalizing: Callable[[], bool] = sys.is_finalizing, _suppress: type[suppress] = suppress
    ) -> None:
        # Module teardown can clear globals before this finalizer runs.
        with _suppress(*((Exception,) if _is_finalizing() else (sqlite3.Error, RuntimeError, OSError))):
            self.close()

    @override
    def close(self) -> None:
        with sqlite_transition(), fork_transition():
            if GETPID() != self.creator_pid:  # pragma: needs fork
                return
            sqlite3.Connection.close(self)
            try:
                if (directory := self._database_directory) is not None:  # pragma: needs posix-hard-link
                    self._database_directory = None
                    remove_link_directory(directory)
            finally:
                if (probe := self._probe) is not None:  # pragma: win32 no cover
                    self._probe = self.database_identity = None
                    PROBE_DESCRIPTORS.release(probe)
            if (decrement := self._decrement_escrow) is not None:  # pragma: <3.12 cover  # pragma: needs fork
                self._decrement_escrow = None
                decrement(self)

    def retain_link(self, directory: LinkDirectory | None) -> None:  # pragma: win32 cover
        self._database_directory = directory

    def retain_until_close(self, directory: LinkDirectory | None, probe: _Probe) -> None:  # pragma: win32 no cover
        self._database_directory = directory
        self._probe = probe
        self.database_identity = probe.identity

    def acquire_escrow(  # pragma: <3.12 cover  # pragma: needs fork
        self,
        functions: tuple[Callable[[sqlite3.Connection], None], Callable[[sqlite3.Connection], None]],
    ) -> None:
        increment, decrement = functions
        increment(self)
        self._decrement_escrow = decrement


class OwnedConnection:
    # The singleton cache can still return the lock during its finalizer. Only its connection owner closes SQLite.
    __slots__ = ("connection", "identity", "transaction_released")

    def __init__(self) -> None:
        self.connection: ForkSafeConnection | None = None
        self.transaction_released = True
        self.identity: DatabaseIdentity | None = None

    def __del__(
        self, _is_finalizing: Callable[[], bool] = sys.is_finalizing, _suppress: type[suppress] = suppress
    ) -> None:
        # Module teardown can clear globals before this finalizer runs.
        if (connection := self.connection) is not None:
            with _suppress(*((Exception,) if _is_finalizing() else (sqlite3.Error, RuntimeError))):
                connection.close()


class _ProbeDescriptors(ForkResettable):
    # Closing any probe drops this process's POSIX locks on its inode. Keep all probes until the last release.
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._inodes: dict[DatabaseIdentity, _InodeProbes] = {}
        self._releases: deque[_Probe] = deque()
        self._leases = count()

    def adopt(self, database: str, claimed: list[_Probe]) -> _Probe | None:  # pragma: win32 no cover
        # An idle probe avoids keeping another descriptor open until the last connection closes.
        try:
            stat_result: Final[os.stat_result] = os.lstat(database)
        except OSError:
            return None
        identity: Final[tuple[int, int]] = stat_result.st_dev, stat_result.st_ino
        with self._lock:
            if not stat.S_ISREG(stat_result.st_mode) or not (probes := self._inodes.get(identity)) or not probes.idle:
                return None
            claimed.append(adopted := _Probe(identity=identity, fd=probes.idle.pop(), lease=next(self._leases)))
            probes.leases.add(adopted.lease)
        return adopted

    def retain(self, fd: int, claimed: list[_Probe]) -> _Probe:  # pragma: win32 no cover
        stat_result: Final[os.stat_result] = os.fstat(fd)
        identity: Final[tuple[int, int]] = stat_result.st_dev, stat_result.st_ino
        token: Final[int | None] = register_owned_descriptor(fd, identity)
        with self._lock:
            (probes := self._inodes.setdefault(identity, _InodeProbes())).descriptors.append((fd, token))
            claimed.append(retained := _Probe(identity=identity, fd=fd, lease=next(self._leases)))
            probes.leases.add(retained.lease)
        return retained

    def release(self, probe: _Probe) -> None:  # pragma: win32 no cover
        # A finalizer can interrupt the thread holding the probe lock.
        self._releases.append(probe)
        self.drain()

    def drain(self) -> None:  # pragma: win32 no cover
        while self._releases and self._lock.acquire(blocking=False):
            try:
                # Keep interrupted releases queued for the next drain.
                while self._releases:
                    self._release_locked(self._releases[0])
                    self._releases.popleft()
            finally:
                self._lock.release()

    def _release_locked(self, probe: _Probe) -> None:  # pragma: win32 no cover
        if (probes := self._inodes.get(probe.identity)) is None:
            return
        if probe.lease in probes.leases:
            probes.leases.remove(probe.lease)
            if probes.leases:
                probes.idle.append(probe.fd)
        if probes.leases:
            return
        # No connect may adopt a probe about to close, even one an interrupt leaves listed.
        probes.idle.clear()
        # Closing under the lock keeps a concurrent connect from taking a lock on this inode before the close.
        while probes.descriptors:
            fd, token = probes.descriptors[-1]
            if token is not None:  # pragma: needs fork
                unregister_owned_descriptor(token)
            # A retry after an interrupted close must never close a reused descriptor.
            probes.descriptors.pop()
            with suppress(OSError):
                os.close(fd)
        del self._inodes[probe.identity]

    @override
    def _reset_after_fork_in_child(self) -> None:  # pragma: forked child
        # The child holds no POSIX locks, and the owned-descriptor registry closes the inherited probes.
        self._lock = threading.Lock()
        self._inodes = {}
        self._releases = deque()


@dataclass(frozen=True, slots=True, kw_only=True)
class _Probe:
    identity: DatabaseIdentity
    fd: int
    # One per connection, so a release applied again after an interrupt kept it queued counts once.
    lease: int


@dataclass(frozen=True, slots=True, kw_only=True)
class _InodeProbes:
    leases: set[int] = field(default_factory=set)
    descriptors: list[tuple[int, int | None]] = field(default_factory=list)
    idle: list[int] = field(default_factory=list)


PROBE_DESCRIPTORS: Final[_ProbeDescriptors] = _ProbeDescriptors()


__all__ = [
    "PROBE_DESCRIPTORS",
    "ForkSafeConnection",
    "OwnedConnection",
    "bounded_schema",
    "connect",
]
