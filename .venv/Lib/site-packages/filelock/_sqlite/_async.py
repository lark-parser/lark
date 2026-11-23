"""Async wrapper around :class:`ReadWriteLock` for use with ``asyncio``."""

from __future__ import annotations

__lazy_modules__ = ["concurrent.futures", "sqlite3"]

import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from filelock._async_lock import AsyncReadWriteBase, AsyncReadWriteProxy
from filelock._core import (
    append_exception_context,
    ensure_current_process,
    fork_transition,
    override,
    register_fork_object,
)

from ._lock import ReadWriteLock

if TYPE_CHECKING:
    import asyncio
    from collections.abc import AsyncGenerator
    from concurrent import futures
    from typing import Literal


class AsyncReadWriteLock(AsyncReadWriteBase[ReadWriteLock]):
    """
    Task-owned SQLite reader/writer lock. Queued writers precede new readers.
    A task may reenter its current mode. Changing mode while holding the lock raises :class:`RuntimeError`.

    :param lock_file: SQLite lock database
    :param timeout: seconds to wait. A value of ``-1`` uses SQLite's busy-timeout limit of about 23 days.
    :param blocking: raise :class:`~filelock.Timeout` immediately on contention when false
    :param is_singleton: share the backend and its task holds across wrappers for this path
    :param loop: event loop for executor calls, defaulting to the running loop
    :param executor: caller-owned executor. The default is a dedicated worker joined by :meth:`close`.

    .. versionadded:: 3.21.0
    """

    def __init__(  # ruff:ignore[too-many-arguments]  # public constructor: one parameter per documented lock option
        self,
        lock_file: str | os.PathLike[str],
        timeout: float = -1,
        *,
        blocking: bool = True,
        is_singleton: bool = True,
        loop: asyncio.AbstractEventLoop | None = None,
        executor: futures.Executor | None = None,
    ) -> None:
        super().__init__(is_singleton=is_singleton)
        self._fork_invalidated = False
        with fork_transition():
            self._bind(ReadWriteLock(lock_file, timeout, blocking=blocking, is_singleton=is_singleton), loop, executor)
            self._executor = executor or ThreadPoolExecutor(max_workers=1)
            # The child reset needs a fully initialized executor.
            register_fork_object(self)
            if os.getpid() != self._creator_pid:  # pragma: forked child
                msg = "AsyncReadWriteLock construction cannot continue after fork"
                raise RuntimeError(msg)

    @asynccontextmanager
    async def read_lock(self, timeout: float | None = None, *, blocking: bool | None = None) -> AsyncGenerator[None]:
        """
        Hold the lock until the context exits. See :meth:`acquire_read` for acquisition errors.

        :param timeout: seconds to wait, or ``None`` for the instance default
        :param blocking: wait on contention, or ``None`` for the instance default
        :yields: while the lock is held
        """
        await self.acquire_read(timeout, blocking=blocking)
        body_error: BaseException | None = None
        try:
            yield
        except BaseException as error:
            body_error = error
            raise
        finally:
            await self._release_in_context(body_error)

    async def acquire_read(
        self, timeout: float | None = None, *, blocking: bool | None = None
    ) -> AsyncAcquireReadWriteReturnProxy:
        """
        Acquire a shared read lock for the current task.

        :param timeout: seconds to wait, or ``None`` for the instance default
        :param blocking: wait on contention, or ``None`` for the instance default
        :returns: an async context manager that releases the lock on exit
        :raises RuntimeError: the task already holds the write lock or inherited the wrapper after fork
        :raises sqlite3.ProgrammingError: the wrapper is closed
        :raises Timeout: the deadline expired
        :raises TypeError: timeout is a boolean or not a real number, or blocking is not a boolean
        :raises ValueError: a blocking call received NaN or a negative timeout other than -1
        """
        self._raise_if_unusable()
        await self._acquire("read", timeout, blocking=blocking)
        return AsyncAcquireReadWriteReturnProxy(lock=self)

    @override
    def _raise_if_unusable(self) -> None:
        ensure_current_process()
        if self._inherited:  # pragma: needs fork
            msg = f"AsyncReadWriteLock on {self.lock_file} was invalidated by fork(); construct a new instance"
            raise RuntimeError(msg)
        if self._closed:
            msg = "Cannot operate on a closed database."
            raise sqlite3.ProgrammingError(msg)

    @property
    @override
    def _inherited(self) -> bool:
        return self._fork_invalidated or super()._inherited

    async def _acquire(self, mode: Literal["read", "write"], timeout: float | None, *, blocking: bool | None) -> None:
        await self._admit(
            mode,
            self.timeout if timeout is None else timeout,
            blocking=self.blocking if blocking is None else blocking,
        )

    async def _release_in_context(self, body_error: BaseException | None) -> None:
        try:
            await self.release()
        except BaseException as release_error:
            if body_error is not None:
                append_exception_context(release_error, body_error)
            raise

    @asynccontextmanager
    async def write_lock(self, timeout: float | None = None, *, blocking: bool | None = None) -> AsyncGenerator[None]:
        """
        Hold the lock until the context exits. See :meth:`acquire_write` for acquisition errors.

        :param timeout: seconds to wait, or ``None`` for the instance default
        :param blocking: wait on contention, or ``None`` for the instance default
        :yields: while the lock is held
        """
        await self.acquire_write(timeout, blocking=blocking)
        body_error: BaseException | None = None
        try:
            yield
        except BaseException as error:
            body_error = error
            raise
        finally:
            await self._release_in_context(body_error)

    async def acquire_write(
        self, timeout: float | None = None, *, blocking: bool | None = None
    ) -> AsyncAcquireReadWriteReturnProxy:
        """
        Acquire an exclusive write lock for the current task.

        :param timeout: seconds to wait, or ``None`` for the instance default
        :param blocking: wait on contention, or ``None`` for the instance default
        :returns: an async context manager that releases the lock on exit
        :raises RuntimeError: the task already holds the read lock or inherited the wrapper after fork
        :raises sqlite3.ProgrammingError: the wrapper is closed
        :raises Timeout: the deadline expired
        :raises TypeError: timeout is a boolean or not a real number, or blocking is not a boolean
        :raises ValueError: a blocking call received NaN or a negative timeout other than -1
        """
        self._raise_if_unusable()
        await self._acquire("write", timeout, blocking=blocking)
        return AsyncAcquireReadWriteReturnProxy(lock=self)

    @override
    def _reset_after_fork_in_child(self) -> None:  # pragma: forked child
        self._fork_invalidated = True
        self._forget_inherited_workers()


class AsyncAcquireReadWriteReturnProxy(AsyncReadWriteProxy[AsyncReadWriteLock]):
    """
    Context-aware object that releases the async read/write lock on exit.

    :param lock: the lock to release on exit
    """

    def __init__(self, lock: AsyncReadWriteLock) -> None:
        super().__init__(lock)

    @override
    async def __aenter__(self) -> AsyncReadWriteLock:
        return self.lock


__all__ = [
    "AsyncAcquireReadWriteReturnProxy",
    "AsyncReadWriteLock",
]
