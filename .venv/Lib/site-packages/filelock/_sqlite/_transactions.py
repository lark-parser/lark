"""SQLite read and write transactions with lock acquisition deadlines."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    assert __spec__ is not None

__lazy_modules__ = [
    "contextlib",
    "filelock._core",
    "pathlib",
    "sqlite3",
    f"{__spec__.parent}._connection",
    f"{__spec__.parent}._fork",
]

import logging
import os
import pathlib
import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal

from filelock._core import Timeout, canonical, raise_chained_errors

from ._connection import ForkSafeConnection, OwnedConnection, bounded_schema, connect
from ._fork import CONNECTION_ESCROW, FORKED_DATABASES, GETPID, sqlite_transition

if TYPE_CHECKING:
    from collections.abc import Callable

_LOGGER: Final[logging.Logger] = logging.getLogger("filelock")
CANCEL_POLL_INTERVAL: Final[float] = 0.1


@dataclass(frozen=True, slots=True, kw_only=True)
class Operation:
    pid: int
    start_time: float
    cancel_check: Callable[[], bool] | None


class DatabaseTransaction:
    def __init__(self, lock_file: str | os.PathLike[str]) -> None:
        self.lock_file = os.fspath(lock_file)
        self._canonical_path = pathlib.Path(canonical(lock_file))
        FORKED_DATABASES.raise_if_poisoned(self._canonical_path)
        self._owned_connection = OwnedConnection()
        self._creator_pid = GETPID()
        self._fork_invalidated = False

    def _transaction_ended(self) -> bool:
        if self._owned_connection.transaction_released or (connection := self._con) is None:
            return True
        # An interrupt can land between the rollback and the flag that records it.
        return not connection.in_transaction

    @property
    def _con(self) -> ForkSafeConnection | None:
        return self._owned_connection.connection

    def _finish_connection(self) -> None:
        with sqlite_transition():
            if (connection := self._con) is None:
                return
            rollback_error: sqlite3.Error | None = None
            if not self._owned_connection.transaction_released:
                if connection.in_transaction:
                    try:
                        connection.rollback()
                    except sqlite3.Error as error:
                        if connection.in_transaction:
                            raise
                        self._owned_connection.transaction_released = True
                        rollback_error = error
                    else:
                        self._owned_connection.transaction_released = True
                else:
                    self._owned_connection.transaction_released = True
            try:
                connection.close()
            except sqlite3.Error as close_error:
                if rollback_error is not None:
                    raise_chained_errors(rollback_error, close_error)
                raise
            self._owned_connection.connection = None
            self._owned_connection.transaction_released = True
            self._owned_connection.identity = None
            if rollback_error is not None:
                raise rollback_error

    def _open_for_acquisition(self, timeout: float, *, blocking: bool, operation: Operation) -> ForkSafeConnection:
        with sqlite_transition():
            sqlite_timeout = (
                _timeout_for_sqlite(
                    timeout,
                    blocking=blocking,
                    already_waited=time.perf_counter() - operation.start_time,
                )
                / 1000
            )
            connection = self._open_waiting(sqlite_timeout, cancel_check=operation.cancel_check)
            owned = self._owned_connection
            owned.connection, owned.transaction_released, owned.identity = (
                connection,
                False,
                FORKED_DATABASES.identity(self._canonical_path),
            )
            self._raise_if_process_changed(operation.pid)
            return connection

    def _open_waiting(self, timeout: float, *, cancel_check: Callable[[], bool] | None) -> ForkSafeConnection:
        deadline = time.perf_counter() + timeout
        while True:
            try:
                return self._open_connection(sqlite_timeout=timeout)
            except Timeout:
                remaining = deadline - time.perf_counter()
                if remaining <= 0 or (cancel_check is not None and cancel_check()):
                    raise
                time.sleep(min(remaining, CANCEL_POLL_INTERVAL))
                timeout = deadline - time.perf_counter()
                if timeout <= 0:
                    raise

    def _open_connection(self, *, sqlite_timeout: float) -> ForkSafeConnection:
        with sqlite_transition():
            creator_pid = GETPID()
            functions = CONNECTION_ESCROW.functions()
            if GETPID() != creator_pid:  # pragma: forked child
                msg = "SQLite connection construction cannot continue after fork"
                raise RuntimeError(msg)
            try:
                connection = connect(
                    os.fspath(self._canonical_path),
                    factory=ForkSafeConnection,
                    timeout=sqlite_timeout,
                )
            except BlockingIOError:
                raise Timeout(self.lock_file) from None
            if functions is not None:  # pragma: <3.12 cover  # pragma: needs fork
                connection.acquire_escrow(functions)
            if GETPID() != creator_pid:  # pragma: forked child
                FORKED_DATABASES.poison_after_fork(
                    self._canonical_path,
                    FORKED_DATABASES.identity(self._canonical_path),
                )
                msg = "SQLite connection construction cannot continue after fork"
                raise RuntimeError(msg)
            return connection

    def _raise_if_process_changed(self, operation_pid: int) -> None:
        if GETPID() != operation_pid or self._inherited:  # pragma: forked child
            msg = f"ReadWriteLock on {self.lock_file} was invalidated by fork(); construct a new instance"
            raise RuntimeError(msg)

    @property
    def _inherited(self) -> bool:
        return self._fork_invalidated or GETPID() != self._creator_pid

    def _configure_and_begin(
        self,
        connection: ForkSafeConnection,
        mode: Literal["read", "write"],
        timeout: float,
        *,
        blocking: bool,
        operation: Operation,
    ) -> None:
        with sqlite_transition():
            # SQLite's first statement can replay a journal beside the database it opened.
            self._raise_if_database_replaced(connection)
            with bounded_schema(connection, self.lock_file):
                self._raise_if_process_changed(operation.pid)
                # WAL permits other readers during an exclusive write transaction.
                self._execute_waiting(
                    connection, ("PRAGMA journal_mode=MEMORY",), timeout, blocking=blocking, operation=operation
                )
                self._raise_if_process_changed(operation.pid)
                statements = ("BEGIN EXCLUSIVE TRANSACTION",)
                if mode == "read":
                    # A deferred read transaction needs a SELECT to acquire its shared lock.
                    statements = ("BEGIN TRANSACTION", "SELECT name FROM sqlite_master LIMIT 1")
                elif blocking and operation.cancel_check is None and not 0 <= timeout <= CANCEL_POLL_INTERVAL:
                    # Keep the writer reservation across busy retries while the previous writer finishes.
                    self._execute_waiting(
                        connection,
                        ("BEGIN IMMEDIATE", "PRAGMA locking_mode=EXCLUSIVE", "ROLLBACK"),
                        timeout,
                        blocking=blocking,
                        operation=operation,
                    )
                    statements += ("PRAGMA locking_mode=NORMAL",)
                self._execute_waiting(connection, statements, timeout, blocking=blocking, operation=operation)
                # SQLite rereads the header while BEGIN waits; a pre-connect check can miss a switch to WAL.
                with closing(connection.execute("PRAGMA journal_mode;")) as cursor:
                    if ("wal",) in cursor.fetchall():
                        msg = f"refusing a lock database switched to WAL mode while acquiring: {self.lock_file!r}"
                        raise ValueError(msg)
                if mode == "write":
                    # BEGIN EXCLUSIVE can succeed on a read-only connection.
                    with closing(connection.execute("PRAGMA user_version;")) as cursor:
                        (version,) = cursor.fetchone()
                    connection.execute(f"PRAGMA user_version={int(version)};").close()
            self._raise_if_database_replaced(connection)

    def _raise_if_database_replaced(self, connection: ForkSafeConnection) -> None:
        # SQLite opens Windows databases without delete sharing.
        if (identity := connection.database_identity) is None:  # pragma: win32 cover
            return
        try:  # pragma: win32 no cover
            current = self._canonical_path.stat(follow_symlinks=False)
        except FileNotFoundError:  # pragma: win32 no cover
            current = None
        # The lock follows the inode, but the next caller opens the name.
        if current is None or (current.st_dev, current.st_ino) != identity:  # pragma: win32 no cover
            msg = f"lock database {self.lock_file!r} was unlinked or replaced while acquiring; leave it in place"
            raise OSError(msg)

    @staticmethod
    def _execute_waiting(
        connection: ForkSafeConnection,
        statements: tuple[str, ...],
        timeout: float,
        *,
        blocking: bool,
        operation: Operation,
    ) -> None:
        budget_ms = _timeout_for_sqlite(timeout, blocking=blocking, already_waited=0)
        slice_ms = int(CANCEL_POLL_INTERVAL * 1000)
        while True:
            remaining_ms = max(0, budget_ms - int((time.perf_counter() - operation.start_time) * 1000))
            try:
                # PyPy can only finalize interrupted statements at close if execute() registered them.
                connection.execute(f"PRAGMA busy_timeout={min(remaining_ms, slice_ms)}").close()
                for statement in statements:
                    connection.execute(statement).close()
            except sqlite3.OperationalError as error:
                if (
                    remaining_ms <= slice_ms
                    or error.sqlite_errorcode != sqlite3.SQLITE_BUSY
                    or (operation.cancel_check is not None and operation.cancel_check())
                ):
                    raise
                # A read's BEGIN succeeds before its SELECT waits, so the retry has to start a fresh transaction.
                if connection.in_transaction:
                    connection.rollback()
            else:
                return


def _timeout_for_sqlite(timeout: float, *, blocking: bool, already_waited: float) -> int:
    if blocking is False:
        return 0

    # SQLite's busy timeout must fit in a signed C int.
    max_timeout_ms = 2_000_000_000 - 1
    if timeout == -1:
        return max_timeout_ms

    if timeout < 0:
        msg = "timeout must be a non-negative number or -1"
        raise ValueError(msg)

    timeout_ms = int((max(timeout - already_waited, 0) if timeout > 0 else timeout) * 1000)
    if timeout_ms > max_timeout_ms or timeout_ms < 0:
        _LOGGER.warning("timeout %s is too large for SQLite, using %s ms instead", timeout, max_timeout_ms)
        return max_timeout_ms
    return timeout_ms


__all__ = [
    "CANCEL_POLL_INTERVAL",
    "DatabaseTransaction",
    "Operation",
]
