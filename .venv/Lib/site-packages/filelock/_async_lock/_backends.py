"""Async adapters for native, soft and reader/writer locks."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    assert __spec__ is not None

__lazy_modules__ = [
    "asyncio",
    "concurrent",
    "concurrent.futures",
    "functools",
    "threading",
    f"{__spec__.parent}._executor",
    f"{__spec__.parent}._owners",
]

import asyncio
import functools
import os
import threading
from abc import abstractmethod
from concurrent import futures
from concurrent.futures import Future as ConcurrentFuture
from typing import TYPE_CHECKING, Final, Generic, Literal, ParamSpec, TypeVar, cast

from filelock._core import ForkResettable, ReadWriteBackend, Timeout, ensure_current_process
from filelock._native import UnixFileLock, WindowsFileLock
from filelock._soft import SoftFileLease, SoftFileLock, StrictSoftFileLock

from ._executor import (
    AsyncClose,
    BackendOutcome,
    drain_future,
    future_result,
    raise_cancelled_error,
    submit_call,
    wait_until_done,
)
from ._lock import BaseAsyncFileLock
from ._owners import TASKS_THREAD_ID, task_owners_for

if TYPE_CHECKING:
    from collections.abc import Callable, MutableMapping
    from concurrent.futures import ThreadPoolExecutor
    from types import TracebackType

    from filelock import AsyncReadWriteLock, AsyncSoftReadWriteLock
    from filelock._core import AcquireReturnProxy


class AsyncSoftFileLock(SoftFileLock, BaseAsyncFileLock):
    """An asynchronous marker-file lock."""

    __module__ = "filelock.asyncio"

    _lifetime_replacements: tuple[str, str] | None = ("AsyncStrictSoftFileLock", "AsyncSoftFileLease")


class AsyncStrictSoftFileLock(StrictSoftFileLock, BaseAsyncFileLock):
    """An asynchronous lock backed by strict owner claims."""

    __module__ = "filelock.asyncio"

    _timed_release_supported = False


class AsyncSoftFileLease(SoftFileLease, BaseAsyncFileLock):
    """A renewable marker lease that a peer can take after expiry."""

    __module__ = "filelock.asyncio"


class AsyncUnixFileLock(UnixFileLock, BaseAsyncFileLock):
    """An asynchronous Unix lock backed by :func:`fcntl.flock`."""

    __module__ = "filelock.asyncio"


class AsyncWindowsFileLock(WindowsFileLock, BaseAsyncFileLock):
    """An asynchronous Windows byte-range lock."""

    __module__ = "filelock.asyncio"


_P = ParamSpec("_P")
_R = TypeVar("_R")
_Backend = TypeVar("_Backend", bound=ReadWriteBackend)


class AsyncReadWriteBase(ForkResettable, Generic[_Backend]):
    _executor: futures.Executor

    def __init__(self, *, is_singleton: bool) -> None:
        self._creator_pid = os.getpid()
        self._closed = False
        self._close_state = AsyncClose()
        self._closing: ConcurrentFuture[None] | None = None
        self._owns_backend = not is_singleton
        # Singleton wrappers share a backend hold. Closing one must retire only that wrapper's levels.
        self._via: Final = object()

    def __del__(self, _getpid: Callable[[], int] = os.getpid) -> None:
        # Module teardown can clear os before the executor is finalized.
        if _getpid() == getattr(self, "_creator_pid", None) and getattr(self, "_owns_executor", False):
            self._executor.shutdown(wait=False)

    @property
    def loop(self) -> asyncio.AbstractEventLoop | None:
        """Loop, or ``None`` for the running loop."""  # simplint: ignore[function-docstring]  # inherited public API
        return self._loop

    @property
    def executor(self) -> futures.Executor:
        """Supplied executor or the owned worker."""  # simplint: ignore[function-docstring]  # inherited public API
        return self._executor

    @property
    def timeout(self) -> float:
        """The default timeout."""  # simplint: ignore[function-docstring]  # inherited public API
        return self._lock.timeout

    @property
    def blocking(self) -> bool:
        """Whether blocking is enabled by default."""  # simplint: ignore[function-docstring]  # inherited public API
        return self._lock.blocking

    def _bind(self, lock: _Backend, loop: asyncio.AbstractEventLoop | None, executor: futures.Executor | None) -> None:
        self._lock = lock
        self._owners = task_owners_for(lock)
        self._loop = loop
        self._owns_executor = executor is None

    async def _admit(self, mode: Literal["read", "write"], timeout: float, *, blocking: bool) -> None:
        async def enter(remaining: float) -> None:
            # A concurrent close can finish while this task waits its turn.
            self._raise_if_unusable()
            await self._run_acquire(
                functools.partial(
                    self._lock._acquire_level_of,  # ruff:ignore[private-member-access]  # wrapper-owned backend hold
                    TASKS_THREAD_ID,
                    mode,
                    remaining,
                    blocking=blocking,
                )
            )

        await self._owners.acquire(
            mode,
            timeout=timeout,
            blocking=blocking,
            lock_file=self.lock_file,
            via=self._via,
            enter=enter,
            joinable=functools.partial(self._joinable, mode),
            raise_if_unusable=self._raise_if_unusable,
            check_after_enter=self._check_after_enter,
        )

    @abstractmethod
    def _raise_if_unusable(self) -> None: ...

    async def _run_acquire(self, acquire: functools.partial[AcquireReturnProxy]) -> None:
        abandoned = threading.Event()
        acquire_future = self._submit(acquire, cancel_check=lambda: abandoned.is_set() or self._closed)
        try:
            await wait_until_done(acquire_future)
        except asyncio.CancelledError as cancellation:
            # A blocked worker must observe cancellation before trying again.
            abandoned.set()
            try:
                await drain_future(acquire_future)
            except Timeout:
                raise cancellation from None
            except BaseException as error:  # ruff:ignore[blind-except]  # reported with the cancellation below
                raise_cancelled_error(cancellation, error)
            try:
                await drain_future(self._submit(self._leave_backend))
            except BaseException as error:  # ruff:ignore[blind-except]  # reported with the cancellation below
                raise_cancelled_error(cancellation, error)
            raise
        try:
            future_result(acquire_future)
        except Timeout:
            self._raise_if_unusable()
            raise

    def _submit(
        self, func: Callable[_P, _R], *args: _P.args, **kwargs: _P.kwargs
    ) -> asyncio.Future[BackendOutcome[_R]]:
        return submit_call(
            self._loop or asyncio.get_running_loop(), self._executor, functools.partial(func, *args, **kwargs)
        )

    def _leave_backend(self) -> None:
        # A synchronous user of this singleton keeps its own level.
        self._lock._release_level_of(TASKS_THREAD_ID)  # ruff:ignore[private-member-access]  # wrapper-owned level

    @property
    def lock_file(self) -> str:
        """The path to the lock file."""  # simplint: ignore[function-docstring]  # inherited public API
        return self._lock.lock_file

    def _joinable(self, _mode: Literal["read", "write"], /) -> bool:
        self._raise_if_unusable()
        return self._backend_holds()

    def _backend_holds(self) -> bool:
        # A synchronous close or forced release can end a hold outside the task table.
        return self._lock._holds_level_of(TASKS_THREAD_ID)  # ruff:ignore[private-member-access]  # wrapper-owned level

    async def _check_after_enter(self) -> None:
        cancellation: asyncio.CancelledError | None = None
        while self._closed and (closing := self._closing) is not None:
            try:
                await wait_until_done(asyncio.wrap_future(closing))
            except asyncio.CancelledError as error:
                cancellation = error
        if cancellation is not None:
            if not self._closed:
                try:
                    await self.release(force=True)
                except BaseException as error:  # ruff:ignore[blind-except]  # chain cleanup errors
                    raise_cancelled_error(cancellation, error)
            raise cancellation
        self._raise_if_unusable()

    async def release(self, *, force: bool = False) -> None:
        """
        Release one level held by this task through this wrapper.

        :param force: release every level the task holds through this wrapper
        :raises RuntimeError: no level is held and *force* is false
        """  # simplint: ignore[function-docstring]  # inherited public API
        ensure_current_process()
        if self._inherited:  # pragma: needs fork
            return
        await self._owners.release(
            force=force,
            lock_file=self.lock_file,
            via=self._via,
            leave=functools.partial(self._submit, self._leave_backend),
            still_held=self._backend_holds,
        )

    @property
    def _inherited(self) -> bool:
        return self._creator_pid != os.getpid()

    async def close(self) -> None:
        """
        End this wrapper's holds, wake its waiters, and join its owned worker.

        A singleton backend stays open for other wrappers and synchronous holders. A synchronous close or forced
        release can race with task admission and let a task join an ended hold. A pending acquire that wins its
        hold during close waits for the outcome. It keeps the hold if close fails while the backend is still held.
        """  # simplint: ignore[function-docstring]  # inherited public API
        ensure_current_process()
        if self._inherited:  # pragma: needs fork
            return
        await self._close_state.close(self._retire, self._executor if self._owns_executor else None)

    async def _retire(self) -> None:
        if self._closed:
            return
        # New acquires must see close before the backend starts releasing.
        closing = self._closing = ConcurrentFuture()
        self._closed = True
        try:
            await self._owners.retire(
                None if self._owns_backend else self._via,
                leave=functools.partial(self._submit, self._lock.close if self._owns_backend else self._leave_backend),
                still_held=self._backend_holds,
            )
        except BaseException as error:
            # A failed backend release leaves the hold available for a retry.
            if not isinstance(error, asyncio.CancelledError) and self._backend_holds():
                self._closed = False
            elif self._owns_executor:
                self._executor.shutdown(wait=False)
            raise
        finally:
            self._closing = None
            closing.set_result(None)
            self._owners.wake_via(self._via)

    def _forget_inherited_workers(self) -> None:  # pragma: forked child
        if self._owns_executor:
            # Older runtimes wake vanished workers at child exit and can hang on a queue locked during fork.
            registry = cast(
                "MutableMapping[threading.Thread, object]",
                futures.thread._threads_queues,  # ruff:ignore[private-member-access]  # the exit hook's registry
            )
            pool = cast("ThreadPoolExecutor", self._executor)
            for worker in pool._threads:  # ruff:ignore[private-member-access]  # only the pool lists its workers
                registry.pop(worker, None)


_LockT = TypeVar("_LockT", bound="AsyncReadWriteLock | AsyncSoftReadWriteLock")


class AsyncReadWriteProxy(Generic[_LockT]):
    def __init__(self, lock: _LockT) -> None:
        self.lock: _LockT = lock

    @abstractmethod
    async def __aenter__(self) -> _LockT: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.lock.release()


__all__ = [
    "AsyncReadWriteBase",
    "AsyncReadWriteProxy",
    "AsyncSoftFileLease",
    "AsyncSoftFileLock",
    "AsyncStrictSoftFileLock",
    "AsyncUnixFileLock",
    "AsyncWindowsFileLock",
]
