"""Async lock release during context exit, cancellation and shutdown."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from importlib.machinery import ModuleSpec

__spec__ = cast("ModuleSpec", __spec__)

__lazy_modules__ = ["asyncio", "concurrent", "contextlib", "inspect", f"{__spec__.parent}._executor"]

import asyncio
import contextlib
import logging
import os
from concurrent import futures
from inspect import iscoroutinefunction
from typing import TYPE_CHECKING, Final, NoReturn, cast

from filelock._core import (
    BaseFileLock,
    append_exception_context,
    fork_transition,
    grouped_errors,
    interpreter_exiting,
    is_system_call_failure,
    override,
    raise_body_and_release,
    raise_chained_errors,
    raise_grouped_errors,
)

from ._executor import (
    BackendOutcome,
    capture_awaitable,
    capture_call,
    drain_future,
    future_result,
    run_in_executor,
    wait_until_done,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Coroutine
    from types import TracebackType

    from ._lock import AsyncFileLockContext


_LOGGER: Final[logging.Logger] = logging.getLogger("filelock")
_ASYNC_RELEASE_CANCELLATION_ERRORS: Final[str] = "lock release cancellation and backend release both failed"
_ASYNC_RELEASE_CANCELLATION_MARKER_ATTR: Final[str] = "_filelock_async_release_cancellation"
_ASYNC_RELEASE_CANCELLATION_MARKER: Final[list[None]] = []
_FINALIZER_RELEASES: Final[set[asyncio.Task[None] | futures.Future[None]]] = set()


class AsyncRelease(BaseFileLock):
    _async_context: AsyncFileLockContext

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self._release_in_context(exc_value)

    @override
    async def _release_in_context(  # ty: ignore[incompatible-method-override]  # release is awaited on async locks
        self, body_error: BaseException | None
    ) -> None:
        try:
            await self.release()
        except BaseException as release_error:
            if body_error is None:
                raise
            if self._settings.context_error_policy == "chain":
                append_exception_context(release_error, body_error)
                raise
            if (
                errors := grouped_errors(
                    release_error,
                    _ASYNC_RELEASE_CANCELLATION_ERRORS,
                    (_ASYNC_RELEASE_CANCELLATION_MARKER_ATTR, _ASYNC_RELEASE_CANCELLATION_MARKER),
                )
            ) is not None:
                match errors:
                    # The marker is only ever set on a (CancelledError, backend_error) pair, so this always matches.
                    case (asyncio.CancelledError() as cancellation, backend_error):  # pragma: no branch
                        raise_grouped_errors(
                            "context body, release cancellation, and backend release failed",
                            body_error,
                            cancellation,
                            backend_error,
                        )
            raise_body_and_release(body_error, release_error)

    @override
    async def release(self, force: bool = False) -> None:  # ty: ignore[incompatible-method-override]  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # public API: positional bool kept for backwards compatibility
        """
        Release one lock level. The final release unlocks the file and may delete it, depending on the platform.

        If cancellation interrupts this call while a release is owed, the release finishes before cancellation
        propagates. Retrying it can release another task's level when tasks share the lock.

        :param force: If true, the lock counter is ignored and the lock is released in every case.

        """
        if self._creator_pid != os.getpid() or not self.is_locked:
            return
        async with self._async_context.transition_gate.hold(owed=self._owes_release) as cancellation:
            try:
                await self._release_serialized(force=force)
            except BaseException as release_error:
                if cancellation is not None:
                    self._raise_cancelled_errors(_ASYNC_RELEASE_CANCELLATION_ERRORS, cancellation, release_error)
                raise
        if cancellation is not None:
            raise cancellation

    def _owes_release(self) -> bool:
        return self.is_locked and not self._async_context.releasing_through_backend

    async def _release_serialized(self, *, force: bool) -> None:
        counter_before: Final[int] = self._context.lock_counter
        if not self.is_locked:
            return
        if not force and self._context.lock_counter > 1 and not self._context.unlock_uncertain:
            self._context.lock_counter -= 1
            return

        self._async_context.releasing_through_backend = True
        try:
            await self._release_through_backend()
        except BaseException as release_error:
            if self._release_interrupted_before_commit(counter_before, release_error):
                with contextlib.suppress(Exception):
                    self._release_with_fork_tracking()
                self._commit_release_if_released()
            raise
        finally:
            self._async_context.releasing_through_backend = False

    async def _release_through_backend(self) -> None:
        lock_id, lock_filename = id(self), self.lock_file
        _LOGGER.debug("Attempting to release lock %s on %s", lock_id, lock_filename)
        release_future = self._start_tracked_release()
        try:
            await wait_until_done(release_future)
        except asyncio.CancelledError as cancellation:
            try:
                await drain_future(release_future)
            except BaseException as release_error:  # ruff:ignore[blind-except]  # cancellation and backend failure must both surface
                self._commit_release_if_released()
                self._raise_cancelled_errors(_ASYNC_RELEASE_CANCELLATION_ERRORS, cancellation, release_error)
            self._commit_release()
            raise
        try:
            future_result(release_future)
        except BaseException:  # state follows the backend for control-flow exceptions too
            self._commit_release_if_released()
            raise
        self._commit_release()
        _LOGGER.debug("Lock %s released on %s", lock_id, lock_filename)

    def _start_tracked_release(self) -> asyncio.Future[BackendOutcome[None]]:
        return self._start_internal_method(
            self._release_with_fork_tracking_async
            if iscoroutinefunction(self._release)
            else self._release_with_fork_tracking
        )

    def _start_internal_method(
        self, method: Callable[[], None] | Callable[[], Coroutine[None, None, None]]
    ) -> asyncio.Future[BackendOutcome[None]]:
        if iscoroutinefunction(method):
            return asyncio.create_task(capture_awaitable(cast("Callable[[], Coroutine[None, None, None]]", method)()))
        loop = asyncio.get_running_loop()
        sync_method = cast("Callable[[], None]", method)
        if self.run_in_executor:
            return run_in_executor(loop, self.executor, sync_method)
        future: asyncio.Future[BackendOutcome[None]] = loop.create_future()
        future.set_result(capture_call(sync_method))
        return future

    @property
    def run_in_executor(self) -> bool:
        """Whether synchronous lock operations run on a worker thread."""
        return self._async_context.run_in_executor

    @property
    def executor(self) -> futures.Executor | None:
        """The executor."""
        return self._async_context.executor

    @executor.setter
    def executor(self, value: futures.Executor | None) -> None:
        self._async_context.executor = value

    async def _release_with_fork_tracking_async(self) -> None:
        with fork_transition(self):
            try:
                await cast("Callable[[], Awaitable[None]]", self._release)()
            finally:
                self._unregister_released_descriptor()

    def _release_interrupted_before_commit(self, counter_before: int, release_error: BaseException) -> bool:
        # Only a synchronous backend can receive a signal before committing release.
        return (
            counter_before == self._context.lock_counter
            and self.is_locked
            and not self.run_in_executor
            and not iscoroutinefunction(self._release)
            and not isinstance(release_error, asyncio.CancelledError)
            and not is_system_call_failure(release_error)
        )

    def _commit_release_if_released(self) -> None:
        # An ambiguous unlock error keeps its descriptor for an explicit retry.
        if not self.is_locked:
            self._commit_release()

    def _raise_cancelled_errors(
        self,
        message: str,
        cancellation: asyncio.CancelledError,
        first_error: BaseException,
        second_error: BaseException | None = None,
    ) -> NoReturn:
        if self._settings.context_error_policy == "group":
            marker = (
                (_ASYNC_RELEASE_CANCELLATION_MARKER_ATTR, _ASYNC_RELEASE_CANCELLATION_MARKER)
                if message == _ASYNC_RELEASE_CANCELLATION_ERRORS
                else None
            )
            if second_error is None:
                raise_grouped_errors(message, cancellation, first_error, marker=marker)
            raise_grouped_errors(message, cancellation, first_error, second_error, marker=marker)
        if (context := first_error.__context__) is not None and context is not cancellation:
            if (cancellation_context := cancellation.__context__) is not None:
                append_exception_context(context, cancellation_context)
            cancellation.__context__ = context
        first_error.__context__ = cancellation
        raise_chained_errors(first_error, second_error)

    @property
    def loop(self) -> asyncio.AbstractEventLoop | None:
        """The event loop."""
        return self._async_context.loop

    @override
    def _release_abandoned_holds(self, *, exited_only: bool) -> None:
        with contextlib.suppress(Exception):
            # A synchronous thread-local release also reaches threads whose loops have stopped.
            if self._settings.thread_local and not iscoroutinefunction(self._release):
                self._release_without_loop(exited_only=exited_only)
                return
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                # Daemon event loops may already have stopped during finalization.
                if (loop := self._async_context.loop) is None or loop.is_closed() or interpreter_exiting():
                    self._release_without_loop(exited_only=exited_only)
                    return
                if not loop.is_running():
                    loop.run_until_complete(self.release(force=True))
                    return
                # Off the deadlock registry, a new lock in this task waits for the scheduled release instead of failing.
                self._drop_registry_entry()
                # The stored loop runs in another thread, and only its own thread may create tasks on it.
                pending = asyncio.run_coroutine_threadsafe(self.release(force=True), loop)
            else:
                self._drop_registry_entry()
                pending = loop.create_task(self.release(force=True))
            _FINALIZER_RELEASES.add(pending)
            pending.add_done_callback(self._settle_finalizer_release)

    def _release_without_loop(self, *, exited_only: bool) -> None:
        # Only a synchronous backend can release a hold without an event loop.
        if iscoroutinefunction(self._release):
            return
        if self.is_locked:
            try:
                self._release_with_fork_tracking()
            finally:
                self._commit_release_if_released()
        # A thread-local lock also holds for the threads that ran its loops, and nothing else releases those now.
        self._release_thread_holds(exited_only=exited_only)

    def _settle_finalizer_release(self, pending: asyncio.Task[None] | futures.Future[None]) -> None:
        _FINALIZER_RELEASES.discard(pending)
        # Nothing awaits this release, so a failure or cancellation falls back to the sync release here.
        with contextlib.suppress(asyncio.CancelledError, futures.CancelledError):
            if pending.exception() is None:
                return
        with contextlib.suppress(Exception):
            self._release_without_loop(exited_only=False)


__all__ = [
    "AsyncRelease",
]
