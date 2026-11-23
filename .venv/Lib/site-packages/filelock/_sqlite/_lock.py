"""Synchronous reader/writer locking with SQLite transactions."""

from __future__ import annotations

__lazy_modules__ = ["sqlite3"]

import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from typing import TYPE_CHECKING, ClassVar, Final, Literal
from weakref import WeakValueDictionary

from filelock._core import (
    AcquireReturnProxy,
    ForkClassResettable,
    ForkResettable,
    ReadWriteBackend,
    Timeout,
    acquire_thread_lock,
    ensure_current_process,
    fork_transition,
    override,
    raise_chained_errors,
    register_fork_class,
    register_fork_object,
    resolve_read_write_timeout,
)

from ._connection import PROBE_DESCRIPTORS
from ._fork import CONNECTION_ESCROW, FORKED_DATABASES, GETPID, ReadWriteLockMeta, install_hooks, sqlite_transition
from ._links import LINK_SWEEPS
from ._transactions import CANCEL_POLL_INTERVAL, DatabaseTransaction, Operation

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Callable, Generator


class _Hold:
    __slots__ = ("level", "mode", "read_depths", "write_thread_id")

    def __init__(self) -> None:
        self.level = 0
        self.mode: Literal["read", "write"] | None = None
        self.write_thread_id: int | None = None
        self.read_depths: dict[int, int] = {}

    def grant(self, mode: Literal["read", "write"], holder: int) -> None:
        self.mode, self.level = mode, 1
        if mode == "write":
            self.write_thread_id = holder
        else:
            self.read_depths = {holder: 1}

    def nest(self, mode: Literal["read", "write"], holder: int) -> None:
        if mode == "read":
            self.read_depths[holder] = self.read_depths.get(holder, 0) + 1
        self.level += 1

    def leave_one_level(self, thread_id: int) -> None:
        self.level -= 1
        if self.mode == "read" and (depth := self.read_depths.pop(thread_id) - 1):
            self.read_depths[thread_id] = depth


class ReadWriteLock(
    DatabaseTransaction, ReadWriteBackend, ForkResettable, ForkClassResettable, metaclass=ReadWriteLockMeta
):
    """
    SQLite reader/writer lock. Readers share a transaction. A writer holds it exclusively.

    A thread can nest holds of the same mode. Changing mode raises :class:`RuntimeError`. Each thread can release
    only its own holds. Threads that must wait for a conflicting hold need separate instances with
    ``is_singleton=False``.

    Give the lock a dedicated file on a filesystem supported by SQLite. WAL databases and oversized schemas raise
    :class:`ValueError`. In a directory writable by other accounts, this account also needs write access and
    hard-link support. Protect the directory and its ancestors against replacement.

    :param lock_file: path to the lock database
    :param timeout: default wait in seconds. ``-1`` waits up to SQLite's busy-timeout cap of about 23 days
    :param blocking: whether to wait when the lock is unavailable
    :param is_singleton: reuse the instance for this resolved path

    .. versionadded:: 3.21.0
    """

    _instances: ClassVar[WeakValueDictionary[pathlib.Path, ReadWriteLock]] = WeakValueDictionary()
    _instances_lock = threading.RLock()
    _instances_pid = GETPID()
    _instances_under_construction: ClassVar[set[pathlib.Path]] = set()

    @override
    def __init_subclass__(cls) -> None:
        super().__init_subclass__()
        cls._instances = WeakValueDictionary()
        cls._instances_lock = threading.RLock()
        cls._instances_pid = GETPID()
        cls._instances_under_construction = set()
        register_fork_class(cls)

    def __init__(
        self,
        lock_file: str | os.PathLike[str],
        timeout: float = -1,
        *,
        blocking: bool = True,
        is_singleton: bool = True,  # ruff:ignore[unused-method-argument]  # consumed by ReadWriteLockMeta.__call__
    ) -> None:
        super().__init__(lock_file)
        self.timeout = timeout
        self.blocking = blocking
        self._transaction_lock = threading.Lock()
        self._internal_lock = threading.Lock()
        self._hold = _Hold()
        self._acquisition_thread_ids: set[int] = set()
        self._closed = False
        register_fork_object(self)
        with fork_transition(), sqlite_transition():
            self._open_waiting(5.0, cancel_check=None).close()

    @classmethod
    def get_lock(
        cls, lock_file: str | os.PathLike[str], timeout: float = -1, *, blocking: bool = True
    ) -> ReadWriteLock:
        """
        Get the singleton lock for this path.

        :param lock_file: path to the lock database
        :param timeout: default wait in seconds
        :param blocking: whether to wait on contention
        :returns: the shared instance
        :raises ValueError: the instance already has different defaults
        """
        return cls(lock_file, timeout, blocking=blocking)

    @contextmanager
    def read_lock(self, timeout: float | None = None, *, blocking: bool | None = None) -> Generator[None]:
        """
        Hold a shared read lock for the duration of the context.

        :param timeout: wait in seconds, or ``None`` for the instance default
        :param blocking: whether to wait on contention, or ``None`` for the instance default
        :yields: while the read lock is held
        """
        self.acquire_read(timeout, blocking=blocking)
        try:
            yield
        finally:
            self.release()

    def acquire_read(self, timeout: float | None = None, *, blocking: bool | None = None) -> AcquireReturnProxy:
        """
        Acquire a shared read lock. Repeated acquisitions by the same thread each require a release.

        :param timeout: wait in seconds, or ``None`` for the instance default
        :param blocking: whether to wait on contention, or ``None`` for the instance default
        :returns: a context manager that releases this hold
        :raises RuntimeError: the instance holds a write lock
        :raises Timeout: the lock could not be acquired in time
        """
        return self._acquire(
            "read",
            self.timeout if timeout is None else timeout,
            blocking=self.blocking if blocking is None else blocking,
        )

    @override
    def _acquire(
        self,
        mode: Literal["read", "write"],
        timeout: float,
        *,
        blocking: bool,
        holder: int | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ) -> AcquireReturnProxy:
        timeout = resolve_read_write_timeout(timeout, blocking=blocking)
        start_time: Final[float] = time.monotonic()
        remaining = timeout
        max_transition_wait = 0.05
        while True:
            # Bound each SQLite wait while other Python threads could be waiting to fork.
            final = (
                not blocking
                or 0 <= remaining <= max_transition_wait
                or not hasattr(os, "register_at_fork")
                or threading.active_count() == 1
            )
            try:
                return self._attempt_acquire(
                    mode,
                    remaining if final else max_transition_wait,
                    blocking=blocking,
                    holder=holder,
                    cancel_check=cancel_check,
                )
            except Timeout:
                if final or (cancel_check is not None and cancel_check()):
                    raise
            if timeout != -1:  # pragma: needs register-at-fork
                remaining = max(timeout - (time.monotonic() - start_time), 0)

    def _attempt_acquire(
        self,
        mode: Literal["read", "write"],
        timeout: float,
        *,
        blocking: bool,
        holder: int | None,
        cancel_check: Callable[[], bool] | None,
    ) -> AcquireReturnProxy:
        with fork_transition():
            self._raise_if_unusable()
            operation_pid = GETPID()
            thread_id = threading.get_ident()
            holder = thread_id if holder is None else holder
            with self._internal_lock:
                if self._holds_level():
                    return self._validate_reentrant(mode, holder)
                if thread_id in self._acquisition_thread_ids:  # pragma: no cover - exercised in an audit callback
                    msg = f"Cannot acquire ReadWriteLock on {self.lock_file} while acquisition is active in this thread"
                    raise RuntimeError(msg)
                self._acquisition_thread_ids.add(thread_id)
            try:
                start_time = time.perf_counter()
                self._acquire_transaction_lock(blocking=blocking, timeout=timeout, cancel_check=cancel_check)
                try:
                    self._raise_if_unusable()
                    return self._acquire_transaction(
                        mode,
                        timeout,
                        holder,
                        blocking=blocking,
                        operation=Operation(pid=operation_pid, start_time=start_time, cancel_check=cancel_check),
                    )
                finally:
                    self._transaction_lock.release()
            finally:
                with self._internal_lock:
                    self._acquisition_thread_ids.discard(thread_id)

    def _raise_if_unusable(self) -> None:
        ensure_current_process()
        if self._inherited:  # pragma: needs fork
            msg = f"ReadWriteLock on {self.lock_file} was invalidated by fork(); construct a new instance"
            raise RuntimeError(msg)
        if self._closed:
            msg = "Cannot operate on a closed database."
            raise sqlite3.ProgrammingError(msg)

    def _holds_level(self) -> bool:
        # A release interrupted after its rollback, but before it recorded that, leaves a level with no transaction.
        if self._hold.level > 0 and self._transaction_ended():
            self._clear_lock_state()
        return self._hold.level > 0

    def _clear_lock_state(self) -> None:
        self._hold = _Hold()

    def _validate_reentrant(self, mode: Literal["read", "write"], holder: int) -> AcquireReturnProxy:
        if self._hold.mode != mode:
            opposite = "write" if mode == "read" else "read"
            if holder == self._hold.write_thread_id or holder in self._hold.read_depths:
                direction = "downgrade" if mode == "read" else "upgrade"
                reason = f"already holding a {opposite} lock ({direction} not allowed)"
            else:
                reason = (
                    f"another thread holds a {opposite} lock on this instance, which coordinates processes rather "
                    "than threads; give each thread its own instance with is_singleton=False"
                )
            msg = f"Cannot acquire {mode} lock on {self.lock_file} (lock id: {id(self)}): {reason}"
            raise RuntimeError(msg)
        if mode == "write" and holder != self._hold.write_thread_id:
            msg = (
                f"Cannot acquire write lock on {self.lock_file} (lock id: {id(self)}) "
                f"from thread {holder} while it is held by thread {self._hold.write_thread_id}"
            )
            raise RuntimeError(msg)
        self._hold.nest(mode, holder)
        return AcquireReturnProxy(lock=self)

    def _acquire_transaction_lock(
        self, *, blocking: bool, timeout: float, cancel_check: Callable[[], bool] | None
    ) -> None:
        if not acquire_thread_lock(
            self._transaction_lock,
            blocking=blocking,
            timeout=timeout,
            poll_interval=CANCEL_POLL_INTERVAL,
            cancel_check=cancel_check,
        ):
            raise Timeout(self.lock_file) from None

    def _acquire_transaction(
        self,
        mode: Literal["read", "write"],
        timeout: float,
        holder: int,
        *,
        blocking: bool,
        operation: Operation,
    ) -> AcquireReturnProxy:
        # Another thread can take the hold while we wait for the transaction lock.
        with self._internal_lock:
            if self._holds_level():
                return self._validate_reentrant(mode, holder)
        if self._con is not None:
            self._finish_connection()
        try:
            connection = self._open_for_acquisition(timeout, blocking=blocking, operation=operation)
            self._configure_and_begin(connection, mode, timeout, blocking=blocking, operation=operation)
            self._raise_if_process_changed(operation.pid)
        except BaseException as error:
            acquisition_error: BaseException
            if isinstance(error, sqlite3.OperationalError) and error.sqlite_errorcode == sqlite3.SQLITE_BUSY:
                acquisition_error = Timeout(self.lock_file)
            elif (
                mode == "write"
                and isinstance(error, sqlite3.OperationalError)
                and error.sqlite_errorcode == sqlite3.SQLITE_READONLY
            ):
                acquisition_error = ValueError(f"SQLite opened the lock database read-only: {self.lock_file!r}")
            else:
                acquisition_error = error
            try:
                self._finish_connection()
            except sqlite3.Error as cleanup_error:
                raise_chained_errors(acquisition_error, cleanup_error)
            if acquisition_error is not error:
                raise acquisition_error from None
            raise
        with self._internal_lock:
            self._raise_if_process_changed(operation.pid)
            self._hold.grant(mode, holder)
        return AcquireReturnProxy(lock=self)

    def release(self, *, force: bool = False) -> None:
        """
        Release one level held by this thread.

        :param force: release all levels, including those held by other threads
        :raises RuntimeError: the caller holds no level and *force* is false
        """
        with fork_transition():
            ensure_current_process()
            if self._inherited:  # pragma: needs fork
                return
            self._raise_if_acquiring("release")
            self._release(force=force, close=False)

    def _raise_if_acquiring(self, operation: Literal["close", "release"]) -> None:
        with self._internal_lock:
            active_in_current_thread = threading.get_ident() in self._acquisition_thread_ids
        if active_in_current_thread:  # pragma: no cover - exercised in an audit callback
            msg = f"Cannot {operation} ReadWriteLock on {self.lock_file} while acquisition is active in this thread"
            raise RuntimeError(msg)

    def _release(self, *, force: bool, close: bool, thread_id: int | None = None) -> None:
        thread_id = threading.get_ident() if thread_id is None else thread_id
        with self._transaction_lock, self._internal_lock:
            if not force:
                self._raise_if_not_holder(thread_id)
            if self._hold.level == 0:
                if force and self._con is None:
                    if close:
                        self._closed = True
                    return
                if not force:
                    msg = f"Cannot release a lock on {self.lock_file} (lock id: {id(self)}) that is not held"
                    raise RuntimeError(msg)
            if not force and self._hold.level > 1:
                self._hold.leave_one_level(thread_id)
                return
            try:
                self._finish_connection()
            except BaseException:
                # Rollback drops the hold even when an interrupt prevents cleanup from finishing.
                if self._transaction_ended():
                    self._clear_lock_state()
                raise
            self._clear_lock_state()
            if close:
                self._closed = True

    def _raise_if_not_holder(self, thread_id: int) -> None:
        # SQLite allows cross-thread rollback, which would drop the owning thread's transaction.
        if self._hold.mode == "write" and thread_id != self._hold.write_thread_id:
            msg = (
                f"Cannot release write lock on {self.lock_file} (lock id: {id(self)}) "
                f"from thread {thread_id} while it is held by thread {self._hold.write_thread_id}"
            )
            raise RuntimeError(msg)
        if self._hold.mode == "read" and thread_id not in self._hold.read_depths:
            msg = (
                f"Cannot release read lock on {self.lock_file} (lock id: {id(self)}) "
                f"from thread {thread_id}, which does not hold it"
            )
            raise RuntimeError(msg)

    @contextmanager
    def write_lock(self, timeout: float | None = None, *, blocking: bool | None = None) -> Generator[None]:
        """
        Hold an exclusive write lock for the duration of the context.

        :param timeout: wait in seconds, or ``None`` for the instance default
        :param blocking: whether to wait on contention, or ``None`` for the instance default
        :yields: while the write lock is held
        """
        self.acquire_write(timeout, blocking=blocking)
        try:
            yield
        finally:
            self.release()

    def acquire_write(self, timeout: float | None = None, *, blocking: bool | None = None) -> AcquireReturnProxy:
        """
        Acquire an exclusive write lock. Only its owning thread can reenter or release it.

        :param timeout: wait in seconds, or ``None`` for the instance default
        :param blocking: whether to wait on contention, or ``None`` for the instance default
        :returns: a context manager that releases this hold
        :raises RuntimeError: the instance holds a read lock or another thread owns its write lock
        :raises Timeout: the lock could not be acquired in time
        """
        return self._acquire(
            "write",
            self.timeout if timeout is None else timeout,
            blocking=self.blocking if blocking is None else blocking,
        )

    @override
    def close(self) -> None:
        """Release every hold on this instance, including other threads' holds, and close it."""
        with fork_transition():
            ensure_current_process()
            if self._inherited:  # pragma: needs fork
                return
            self._raise_if_acquiring("close")
            self._release(force=True, close=True)

    @override
    def _release_level_of(self, thread_id: int) -> None:
        with fork_transition():
            ensure_current_process()
            self._raise_if_acquiring("release")
            self._release(force=False, close=False, thread_id=thread_id)

    @override
    def _holds_level_of(self, thread_id: int) -> bool:
        # The event loop must not block on another thread releasing the same transaction.
        if thread_id != self._hold.write_thread_id and thread_id not in self._hold.read_depths:
            return False
        try:
            return not self._transaction_ended()
        except sqlite3.ProgrammingError:
            # The connection closed between the read of _con and the in_transaction call, so the transaction is over.
            return False

    @classmethod
    @override
    def _reset_class_after_fork(cls) -> None:  # pragma: forked child
        cls._instances = WeakValueDictionary()
        cls._instances_lock = threading.RLock()
        cls._instances_pid = GETPID()
        cls._instances_under_construction = set()

    @override
    def _reset_after_fork_in_child(self) -> None:  # pragma: forked child
        if (connection := self._con) is not None:
            # The child can have the same numeric PID as the owner of the private database link.
            connection.creator_pid = None
            FORKED_DATABASES.poison_after_fork(self._canonical_path, self._owned_connection.identity)
        self._owned_connection.connection = None
        self._owned_connection.transaction_released = True
        self._owned_connection.identity = None
        self._transaction_lock = threading.Lock()
        self._internal_lock = threading.Lock()
        self._clear_lock_state()
        self._acquisition_thread_ids = set()
        self._fork_invalidated = True


register_fork_object(LINK_SWEEPS)
register_fork_object(CONNECTION_ESCROW)
register_fork_object(FORKED_DATABASES)
register_fork_object(PROBE_DESCRIPTORS)
register_fork_class(ReadWriteLock)
install_hooks()

__all__ = [
    "ReadWriteLock",
]
