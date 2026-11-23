"""Async wrapper around :class:`SoftReadWriteLock` for use with ``asyncio``."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from importlib.machinery import ModuleSpec

__spec__ = cast("ModuleSpec", __spec__)

__lazy_modules__ = ["concurrent.futures", f"{__spec__.parent}._hold"]

import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

from filelock._async_lock import AsyncReadWriteBase, AsyncReadWriteProxy
from filelock._core import ensure_current_process, override, register_fork_object

from ._hold import lost_hold_error
from ._lock import SoftReadWriteLock

if TYPE_CHECKING:
    import asyncio
    from collections.abc import AsyncGenerator, Callable
    from concurrent import futures
    from typing import Literal

    from filelock import LeaseCompromise


class AsyncSoftReadWriteLock(AsyncReadWriteBase[SoftReadWriteLock]):
    """
    Task-owned reader/writer lock for shared filesystems. Queued writers precede new readers.
    A task may reenter its current mode. Changing mode while holding the lock raises :class:`RuntimeError`.

    Release can raise :class:`~filelock.SoftFileLockProtocolError` if peers win every update until the stale threshold.

    :param lock_file: lock path. The generation log lives under ``<lock_file>.rw``.
    :param timeout: seconds to wait, or ``-1`` to wait indefinitely
    :param blocking: raise :class:`~filelock.Timeout` immediately on contention when false
    :param is_singleton: share the backend and its task holds across wrappers for this path
    :param heartbeat_interval: seconds between heartbeat refreshes
    :param stale_threshold: seconds to wait before evicting an unchanged holder, defaulting to three heartbeat intervals
    :param poll_interval: seconds between retries
    :param on_compromise: callback on the heartbeat thread when the hold is lost
    :param loop: event loop for executor calls, defaulting to the running loop
    :param executor: caller-owned executor. The default is a dedicated worker joined by :meth:`close`.

    .. versionadded:: 3.27.0
    """

    def __init__(  # ruff:ignore[too-many-arguments]  # public constructor: one parameter per documented lock option
        self,
        lock_file: str | os.PathLike[str],
        timeout: float = -1,
        *,
        blocking: bool = True,
        is_singleton: bool = True,
        heartbeat_interval: float = 30.0,
        stale_threshold: float | None = None,
        poll_interval: float = 0.25,
        on_compromise: Callable[[LeaseCompromise], None] | None = None,
        loop: asyncio.AbstractEventLoop | None = None,
        executor: futures.Executor | None = None,
    ) -> None:
        super().__init__(is_singleton=is_singleton)
        lock = SoftReadWriteLock(
            lock_file,
            timeout,
            blocking=blocking,
            is_singleton=is_singleton,
            heartbeat_interval=heartbeat_interval,
            stale_threshold=stale_threshold,
            poll_interval=poll_interval,
            on_compromise=on_compromise,
        )
        self._bind(lock, loop, executor)
        self._executor = ThreadPoolExecutor(max_workers=1) if executor is None else executor
        register_fork_object(self)

    @property
    def generation(self) -> int | None:
        """The current hold's fencing token, or ``None`` when unlocked."""
        return self._lock.generation

    @property
    def compromise(self) -> LeaseCompromise | None:
        """How the hold was lost, or ``None`` while it stands. Acquire raises until the lost hold is released."""
        return self._lock.compromise

    @asynccontextmanager
    async def read_lock(self, timeout: float | None = None, *, blocking: bool | None = None) -> AsyncGenerator[None]:
        """
        Hold the lock until the context exits. See :meth:`acquire_read` for acquisition errors.

        :param timeout: seconds to wait, or ``None`` for the instance default
        :param blocking: wait on contention, or ``None`` for the instance default
        :yields: while the lock is held
        """
        await self.acquire_read(timeout, blocking=blocking)
        try:
            yield
        finally:
            await self.release()

    async def acquire_read(
        self, timeout: float | None = None, *, blocking: bool | None = None
    ) -> AsyncAcquireSoftReadWriteReturnProxy:
        """
        Acquire a shared read lock for the current task.

        :param timeout: seconds to wait, or ``None`` for the instance default
        :param blocking: wait on contention, or ``None`` for the instance default
        :returns: an async context manager that releases the lock on exit
        :raises RuntimeError: the task already holds the write lock, or the wrapper is closed or fork-inherited
        :raises Timeout: the deadline expired
        :raises TypeError: timeout is a boolean or not a real number, or blocking is not a boolean
        :raises ValueError: a blocking call received NaN or a negative timeout other than -1
        """
        self._raise_if_unusable()
        await self._acquire("read", timeout, blocking=blocking)
        return AsyncAcquireSoftReadWriteReturnProxy(lock=self)

    @override
    def _raise_if_unusable(self) -> None:
        ensure_current_process()
        if self._creator_pid != os.getpid():  # pragma: forked child
            msg = f"AsyncSoftReadWriteLock on {self.lock_file} was inherited across fork; construct a new instance"
            raise RuntimeError(msg)
        if self._closed:
            msg = f"AsyncSoftReadWriteLock on {self.lock_file} has been closed"
            raise RuntimeError(msg)

    async def _acquire(self, mode: Literal["read", "write"], timeout: float | None, *, blocking: bool | None) -> None:
        await self._admit(
            mode,
            self._lock.timeout if timeout is None else timeout,
            blocking=self._lock.blocking if blocking is None else blocking,
        )

    @asynccontextmanager
    async def write_lock(self, timeout: float | None = None, *, blocking: bool | None = None) -> AsyncGenerator[None]:
        """
        Hold the lock until the context exits. See :meth:`acquire_write` for acquisition errors.

        :param timeout: seconds to wait, or ``None`` for the instance default
        :param blocking: wait on contention, or ``None`` for the instance default
        :yields: while the lock is held
        """
        await self.acquire_write(timeout, blocking=blocking)
        try:
            yield
        finally:
            await self.release()

    async def acquire_write(
        self, timeout: float | None = None, *, blocking: bool | None = None
    ) -> AsyncAcquireSoftReadWriteReturnProxy:
        """
        Acquire an exclusive write lock for the current task.

        :param timeout: seconds to wait, or ``None`` for the instance default
        :param blocking: wait on contention, or ``None`` for the instance default
        :returns: an async context manager that releases the lock on exit
        :raises RuntimeError: the task already holds the read lock, or the wrapper is closed or fork-inherited
        :raises Timeout: the deadline expired
        :raises TypeError: timeout is a boolean or not a real number, or blocking is not a boolean
        :raises ValueError: a blocking call received NaN or a negative timeout other than -1
        """
        self._raise_if_unusable()
        await self._acquire("write", timeout, blocking=blocking)
        return AsyncAcquireSoftReadWriteReturnProxy(lock=self)

    @override
    def _joinable(self, mode: Literal["read", "write"], /) -> bool:
        self._raise_if_unusable()
        if (compromise := self._lock.compromise) is not None:
            raise lost_hold_error(self.lock_file, mode, compromise)
        return self._backend_holds()

    @override
    def _reset_after_fork_in_child(self) -> None:  # pragma: forked child
        self._creator_pid = -1
        self._forget_inherited_workers()


class AsyncAcquireSoftReadWriteReturnProxy(AsyncReadWriteProxy[AsyncSoftReadWriteLock]):
    """
    Async context-aware object that releases an :class:`AsyncSoftReadWriteLock` on exit.

    :param lock: the lock to release on exit
    """

    def __init__(self, lock: AsyncSoftReadWriteLock) -> None:
        super().__init__(lock)

    @override
    async def __aenter__(self) -> AsyncSoftReadWriteLock:
        return self.lock


__all__ = [
    "AsyncAcquireSoftReadWriteReturnProxy",
    "AsyncSoftReadWriteLock",
]
