"""Base async file lock and its event loop and executor settings."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from importlib.machinery import ModuleSpec

__spec__ = cast("ModuleSpec", __spec__)

__lazy_modules__ = ["asyncio", f"{__spec__.parent}._transitions"]

import asyncio
import os
import time
from dataclasses import dataclass, field, fields
from typing import TYPE_CHECKING, NoReturn, TypeVar

from filelock._core import (
    UNSET_FILE_MODE,
    CloseErrorPolicy,
    ContextErrorPolicy,
    ExtraValue,
    FileLockContext,
    FileLockMeta,
    LockSettings,
    ThreadLocalFileContext,
    Timeout,
    check_blocking,
    delegate_to_current,
    override,
    register_fork_object,
    resolve_poll_interval,
    resolve_timeout,
)

from ._transitions import AsyncTransitionGate, AsyncTransitionUnavailableError

if TYPE_CHECKING:
    from collections.abc import Callable, Hashable, Mapping
    from concurrent import futures
    from types import TracebackType
    from typing import Self

from ._acquire import AsyncAcquisition

_AT = TypeVar("_AT", bound="BaseAsyncFileLock")


class AsyncFileLockMeta(FileLockMeta):
    """Select the executor policy and apply singleton options when constructing an async lock."""

    __module__ = "filelock.asyncio"

    @override
    def __call__(  # ruff:ignore[too-many-arguments]  # forwards the public constructor's documented parameters
        cls: type[_AT],  # ruff:ignore[invalid-first-argument-name-for-method]  # metaclass __call__ receives the class being constructed
        lock_file: str | os.PathLike[str],
        timeout: float = -1,
        mode: int = UNSET_FILE_MODE,
        thread_local: bool = False,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # public API: positional bool kept for backwards compatibility
        *,
        blocking: bool = True,
        is_singleton: bool = False,
        poll_interval: float = 0.05,
        lifetime: float | None = None,
        context_error_policy: ContextErrorPolicy = "chain",
        close_error_policy: CloseErrorPolicy = "default",
        fallback_to_soft: bool = True,
        preserve_lock_file: bool = False,
        on_acquired: Callable[[int], None] | None = None,
        loop: asyncio.AbstractEventLoop | None = None,
        run_in_executor: bool = True,
        executor: futures.Executor | None = None,
        **kwargs: ExtraValue,
    ) -> _AT:
        if thread_local and run_in_executor:
            msg = "run_in_executor is not supported when thread_local is True"
            raise ValueError(msg)
        return super().__call__(
            **kwargs,
            lock_file=lock_file,
            timeout=timeout,
            mode=mode,
            thread_local=thread_local,
            blocking=blocking,
            is_singleton=is_singleton,
            poll_interval=poll_interval,
            lifetime=lifetime,
            context_error_policy=context_error_policy,
            close_error_policy=close_error_policy,
            fallback_to_soft=fallback_to_soft,
            preserve_lock_file=preserve_lock_file,
            on_acquired=on_acquired,
            loop=loop,
            run_in_executor=run_in_executor,
            executor=executor,
        )


class BaseAsyncFileLock(AsyncAcquisition, metaclass=AsyncFileLockMeta):
    """
    Base class for asynchronous file locks.

    .. versionadded:: 3.15.0

    """

    __module__ = "filelock.asyncio"

    _deadlock_holder_desc: str = "BaseAsyncFileLock instance in this task"
    _constructor_lifetime_warning_stacklevel: int = 4

    def __init__(  # ruff:ignore[too-many-arguments]  # public constructor: one parameter per documented lock option
        self,
        lock_file: str | os.PathLike[str],
        timeout: float = -1,
        mode: int = UNSET_FILE_MODE,
        thread_local: bool = False,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # public API: positional bool kept for backwards compatibility
        *,
        blocking: bool = True,
        is_singleton: bool = False,
        poll_interval: float = 0.05,
        lifetime: float | None = None,
        context_error_policy: ContextErrorPolicy = "chain",
        close_error_policy: CloseErrorPolicy = "default",
        fallback_to_soft: bool = True,
        preserve_lock_file: bool = False,
        on_acquired: Callable[[int], None] | None = None,
        loop: asyncio.AbstractEventLoop | None = None,
        run_in_executor: bool = True,
        executor: futures.Executor | None = None,
    ) -> None:
        """
        Create an async lock with the ownership and file options of :class:`~filelock.BaseFileLock`.

        :param lock_file: lock path
        :param timeout: seconds to wait for the lock, negative for unlimited
        :param mode: creation permissions, subject to umask and default ACLs
        :param thread_local: keep settings and holds per thread
        :param blocking: retry until the timeout expires
        :param is_singleton: reuse the instance for the same path
        :param poll_interval: seconds between attempts
        :param lifetime: maximum age of a soft marker before another process can reclaim it
        :param context_error_policy: chain or group errors from the body and release
        :param close_error_policy: whether to propagate native descriptor close errors
        :param fallback_to_soft: allow a Unix lock to use a soft marker when flock is unavailable
        :param preserve_lock_file: keep the native lock pathname on release
        :param on_acquired: callback that borrows the native descriptor after acquisition
        :param loop: fallback loop for finalization outside a running loop
        :param run_in_executor: run synchronous backend operations in a worker thread
        :param executor: worker pool, or the event loop's default pool when omitted

        Use ``thread_local=False`` with an executor. A worker thread cannot share its caller's thread-local hold.
        """
        self._adopt_settings(
            LockSettings(
                thread_local=thread_local,
                is_singleton=is_singleton,
                context_error_policy=context_error_policy,
                close_error_policy=close_error_policy,
                fallback_to_soft=fallback_to_soft,
                preserve_lock_file=preserve_lock_file,
                on_acquired=on_acquired,
            )
        )
        self._async_context = (AsyncThreadLocalFileContext if thread_local else AsyncFileLockContext)(
            lock_file=os.fspath(lock_file),
            timeout=timeout,
            mode=mode,
            blocking=blocking,
            poll_interval=poll_interval,
            lifetime=lifetime,
            loop=loop,
            run_in_executor=run_in_executor,
            executor=executor,
        )
        # BaseFileLock declares _context as FileLockContext; narrowing that writable attribute here is unsound.
        self._context = self._async_context
        register_fork_object(self)

    @override
    def __enter__(self) -> NoReturn:
        """Sync context manager entry is not supported because lock acquisition is a coroutine."""
        msg = "Use `async with`: acquire/release are coroutines and cannot be awaited in a sync context manager."
        raise NotImplementedError(msg)

    @override
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Sync context manager exit is not supported because lock release is a coroutine."""
        msg = "Use `async with`: acquire/release are coroutines and cannot be awaited in a sync context manager."
        raise NotImplementedError(msg)

    async def __aenter__(self) -> Self:
        """
        Acquire the lock.

        :returns: the lock object

        """
        await self.acquire()
        return self

    @override
    async def acquire(  # ty: ignore[incompatible-method-override]  # the async signature differs from the base class
        self,
        timeout: float | None = None,
        poll_interval: float | None = None,
        *,
        blocking: bool | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ) -> AsyncAcquireReturnProxy:
        """
        Acquire the lock and return an async context manager that releases one level on exit.

        :param timeout: seconds to wait, negative for unlimited, or ``None`` for the lock's default
        :param poll_interval: seconds between attempts, or ``None`` for the lock's default
        :param blocking: set to ``False`` for a single attempt
        :param cancel_check: return ``True`` during polling to end the wait
        :raises Timeout: the deadline passed, a nonblocking attempt failed, or *cancel_check* ended the wait
        :raises RuntimeError: a failed native unlock requires an explicit release
        :raises TypeError: *blocking* is not a boolean
        :raises ValueError: invalid timeout or poll interval
        """
        self._raise_if_inherited()
        if timeout is None:
            timeout = self._context.timeout

        if blocking is None:
            blocking = self._context.blocking

        check_blocking(blocking)

        if poll_interval is None:
            poll_interval = self._context.poll_interval
        poll_interval = resolve_poll_interval(poll_interval)
        timeout = resolve_timeout(timeout, blocking=blocking)

        start_time = time.perf_counter()
        try:
            return await self._acquire_with_admission(
                blocking=blocking,
                cancel_check=cancel_check,
                timeout=timeout,
                poll_interval=poll_interval,
                start_time=start_time,
            )
        except AsyncTransitionUnavailableError:
            raise Timeout(self.lock_file) from None

    async def _acquire_with_admission(
        self,
        *,
        blocking: bool,
        cancel_check: Callable[[], bool] | None,
        timeout: float,
        poll_interval: float,
        start_time: float,
    ) -> AsyncAcquireReturnProxy:
        async with self._async_context.transition_gate.hold_for_acquire(
            blocking=blocking,
            cancel_check=cancel_check,
            deadline=None if timeout < 0 else start_time + timeout,
            poll_interval=poll_interval,
        ):
            # Re-entry only counts, so it skips the executor round trip that resolving the path costs.
            if self.is_locked:
                self._raise_if_hold_unusable()
                # A proxy-construction error must leave the existing level unchanged.
                proxy = AsyncAcquireReturnProxy(lock=self)
                self._context.lock_counter += 1
                return proxy
            # A canceled provisional acquire must finish rollback before another caller can claim its descriptor.
            canonical_path = await self._off_loop(self._resolve_lock_path)
            self._async_context.rollback_tried = False
            try:
                self._context.lock_counter = 1
                self._raise_if_would_deadlock(canonical_path, timeout=timeout, blocking=blocking)
                self._pin_lock_path(canonical_path)
                await self._async_poll_until_acquired(
                    blocking=blocking,
                    cancel_check=cancel_check,
                    timeout=timeout,
                    poll_interval=poll_interval,
                    start_time=start_time,
                )
                self._commit_acquire(canonical_path)
                return AsyncAcquireReturnProxy(lock=self)
            except BaseException as error:
                try:
                    if not self._async_context.rollback_tried:
                        await self._rollback_failed_acquire_async(error)
                finally:
                    self._reconcile_failed_acquire(canonical_path, levels_before=0)
                raise

    @staticmethod
    @override
    def _deadlock_scope() -> Hashable | None:
        # Only the owning task can deadlock itself on this event loop.
        return asyncio.current_task()

    @override
    def _singleton_extra_mismatches(self, kwargs: Mapping[str, ExtraValue], /) -> dict[str, tuple[str, str]]:
        mismatches = super()._singleton_extra_mismatches(kwargs)
        # Loops and executors compare by identity: a different one schedules the lock's work elsewhere.
        mismatches.update(
            (name, (str(kwargs[name]), str(value)))
            for name, value in (("loop", self.loop), ("executor", self.executor))
            if kwargs[name] is not value
        )
        if kwargs["run_in_executor"] != self.run_in_executor:
            mismatches["run_in_executor"] = (str(kwargs["run_in_executor"]), str(self.run_in_executor))
        return mismatches


class AsyncAcquireReturnProxy:
    """
    A context-aware object that will release the lock file when exiting.

    :param lock: the lock to release on exit
    """

    __module__ = "filelock.asyncio"

    def __init__(self, lock: BaseAsyncFileLock) -> None:
        self.lock = lock

    async def __aenter__(self) -> BaseAsyncFileLock:
        return self.lock

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.lock._release_in_context(exc_value)  # ruff:ignore[private-member-access]  # releases the wrapped lock's context


def _new_transition_gate() -> AsyncTransitionGate:
    # Called per context rather than passed as the factory, so the lazy import resolves on first use, not at import.
    return AsyncTransitionGate()


@dataclass  # simplint: ignore[dataclass-frozen, dataclass-slots, dataclass-kw-only]  # established mutable context
class AsyncFileLockContext(FileLockContext):
    """
    Settings and ownership state for one asynchronous lock.

    :ivar run_in_executor: whether backend operations run in an executor
    :ivar executor: executor for backend calls, or ``None`` for the event loop's default
    :ivar loop: event loop for backend operations, or ``None`` for the running loop
    :ivar releasing_through_backend: whether backend release is already in progress
    :ivar transition_gate: serializes changes to this context's ownership
    :ivar rollback_tried: whether an interrupted acquisition already attempted rollback
    """

    run_in_executor: bool = True
    executor: futures.Executor | None = None
    loop: asyncio.AbstractEventLoop | None = None

    releasing_through_backend: bool = False

    # Thread-local contexts need separate gates so one thread can release while another waits.
    transition_gate: AsyncTransitionGate = field(default_factory=_new_transition_gate)
    rollback_tried: bool = field(default=False, kw_only=True)


class AsyncThreadLocalFileContext(AsyncFileLockContext, ThreadLocalFileContext):
    """
    Keep separate acquisition state for each thread using the lock.

    :param lock_file: filesystem path used for locking
    :param timeout: default acquisition timeout in seconds
    :param mode: permissions for newly created lock files
    :param blocking: whether acquisition waits on contention
    :param poll_interval: delay between acquisition attempts in seconds
    :param lifetime: maximum age in seconds for a lock subject to expiry
    :param run_in_executor: whether backend operations run in an executor
    :param executor: executor for backend calls, or ``None`` for the event loop's default
    :param loop: event loop for backend operations, or ``None`` for the running loop
    :ivar current: this thread's :class:`~filelock.FileLockContext`, initially an
        :class:`~filelock.asyncio.AsyncFileLockContext`
    """

    # threading.local runs __init__ again with these arguments the first time each thread touches the context.
    def __init__(  # ruff:ignore[too-many-arguments]  # mirrors the AsyncFileLockContext fields set at construction
        self,
        *,
        lock_file: str,
        timeout: float,
        mode: int,
        blocking: bool,
        poll_interval: float,
        lifetime: float | None = None,
        run_in_executor: bool = True,
        executor: futures.Executor | None = None,
        loop: asyncio.AbstractEventLoop | None = None,
    ) -> None:
        self.current = AsyncFileLockContext(
            lock_file=lock_file,
            timeout=timeout,
            mode=mode,
            blocking=blocking,
            poll_interval=poll_interval,
            lifetime=lifetime,
            run_in_executor=run_in_executor,
            executor=executor,
            loop=loop,
        )


# Dataclass annotation lookup during class creation needs the defining module on Python 3.11.
AsyncFileLockContext.__module__ = AsyncThreadLocalFileContext.__module__ = "filelock.asyncio"

for _field in fields(AsyncFileLockContext):
    setattr(AsyncThreadLocalFileContext, _field.name, delegate_to_current(_field.name))


__all__ = [
    "AsyncAcquireReturnProxy",
    "AsyncFileLockContext",
    "AsyncFileLockMeta",
    "AsyncThreadLocalFileContext",
    "BaseAsyncFileLock",
]
