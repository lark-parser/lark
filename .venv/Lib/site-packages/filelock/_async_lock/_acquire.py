"""Acquisition deadlines and rollback for canceled async lock attempts."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from importlib.machinery import ModuleSpec

__spec__ = cast("ModuleSpec", __spec__)

__lazy_modules__ = ["asyncio", "filelock._filesystem", "functools", "inspect", f"{__spec__.parent}._executor"]

import asyncio
import functools
import logging
import time
from inspect import iscoroutinefunction
from typing import TYPE_CHECKING, Final, NoReturn, TypeVar, cast

from filelock._core import (
    Timeout,
    fork_transition,
    override,
    raise_body_and_release,
    raise_chained_errors,
    raise_cleanup_errors,
    raise_grouped_errors,
)
from filelock._filesystem import ensure_directory_exists

from ._executor import (
    drain_future,
    future_result,
    run_in_executor,
    wait_until_done,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

from ._release import AsyncRelease

_LOGGER: Final[logging.Logger] = logging.getLogger("filelock")

_T = TypeVar("_T")


class AsyncAcquisition(AsyncRelease):
    async def _async_poll_until_acquired(
        self,
        *,
        blocking: bool,
        cancel_check: Callable[[], bool] | None,
        timeout: float,
        poll_interval: float,
        start_time: float,
    ) -> None:
        lock_id = id(self)
        lock_filename = self.lock_file
        await self._off_loop(functools.partial(ensure_directory_exists, self._lock_path))
        attempt = 0
        self._set_claim_deadline(start_time, timeout if blocking else 0.0)
        while True:
            self._raise_if_inherited()
            _LOGGER.debug("Attempting to acquire lock %s on %s", lock_id, lock_filename)
            await self._run_acquire_attempt()
            self._raise_if_inherited()
            if self.is_locked:
                _LOGGER.debug("Lock %s acquired on %s", lock_id, lock_filename)
                return
            if self._check_give_up(
                blocking=blocking,
                cancel_check=cancel_check,
                timeout=timeout,
                start_time=start_time,
            ):
                raise Timeout(lock_filename, await self._off_loop(self._unprobeable_holder))
            attempt += 1
            delay = self._poll_delay(poll_interval, attempt)
            if timeout >= 0:
                delay = min(delay, max(start_time + timeout - time.perf_counter(), 0.0))
            _LOGGER.debug("Lock %s not acquired on %s, waiting %s seconds ...", lock_id, lock_filename, delay)
            await asyncio.sleep(delay)

    async def _off_loop(self, call: Callable[[], _T]) -> _T:
        # A slow mount stalls a filesystem call, and the loop with it; a coroutine backend runs on the loop anyway.
        if not self.run_in_executor or iscoroutinefunction(self._acquire):
            return call()
        future = run_in_executor(asyncio.get_running_loop(), self.executor, call)
        await wait_until_done(future)
        return future_result(future)

    async def _run_acquire_attempt(self) -> None:
        acquire_future = self._start_internal_method(
            self._acquire_with_fork_tracking_async
            if iscoroutinefunction(self._acquire)
            else self._break_expired_and_acquire
        )
        try:
            await wait_until_done(acquire_future)
        except asyncio.CancelledError as cancellation:
            acquire_error: BaseException | None = None
            try:
                await drain_future(acquire_future)
            except BaseException as error:  # ruff:ignore[blind-except]  # reported with the cancellation below
                acquire_error = error

            rollback_error: BaseException | None = None
            if self.is_locked:
                try:
                    await self._undo_async_acquire()
                except BaseException as error:  # ruff:ignore[blind-except]  # reported with the cancellation below
                    rollback_error = error

            if acquire_error is not None:
                if rollback_error is not None:  # pragma: needs fcntl
                    self._raise_cancelled_errors(
                        "lock acquisition cancellation, backend attempt, and rollback failed",
                        cancellation,
                        acquire_error,
                        rollback_error,
                    )
                self._raise_cancelled_errors(
                    "lock acquisition cancellation and backend attempt both failed", cancellation, acquire_error
                )
            if rollback_error is not None:
                self._raise_cancelled_errors(
                    "lock acquisition cancellation and rollback both failed", cancellation, rollback_error
                )
            raise
        try:
            future_result(acquire_future)
        except asyncio.CancelledError as acquire_error:
            await self._rollback_backend_cancelled_acquire(acquire_error)

    async def _acquire_with_fork_tracking_async(self) -> None:
        self._try_break_expired_lock()
        with fork_transition(self):
            try:
                await cast("Callable[[], Awaitable[None]]", self._acquire)()
            except BaseException as acquisition_error:
                await self._rollback_failed_acquire_async(acquisition_error)
                raise
            try:
                self._register_context_descriptor()
            except BaseException as registration_error:  # cancellation must roll back the descriptor
                await self._rollback_failed_registration_async(registration_error)
                raise
        if self.is_locked:
            await self._invoke_on_acquired_async()

    async def _rollback_failed_acquire_async(self, acquisition_error: BaseException) -> None:
        if not self.is_locked:
            return
        registration_error: BaseException | None = None
        tracking_error: BaseException | None = None
        try:
            self._register_context_descriptor()
        except BaseException as error:  # ruff:ignore[blind-except]  # preserve registration and acquisition failures
            registration_error = error
            try:
                # Rollback may fail too; retain the fd so a child can close it without another identity probe.
                self._register_unverified_context_descriptor()
            except BaseException as error:  # ruff:ignore[blind-except]  # pragma: no cover - allocation/control-flow during fallback
                tracking_error = error
        try:
            await self._undo_async_acquire()
        except BaseException as rollback_error:  # ruff:ignore[blind-except]  # preserve rollback and acquisition failures
            if registration_error is None and tracking_error is None:
                self._raise_acquire_rollback_errors(acquisition_error, rollback_error)
            raise_cleanup_errors(
                "lock acquisition cleanup failed",
                acquisition_error,
                registration_error,
                tracking_error,
                rollback_error,
            )
        if registration_error is not None:
            raise_cleanup_errors(
                "lock acquisition cleanup failed", acquisition_error, registration_error, tracking_error
            )

    def _raise_acquire_rollback_errors(self, acquire_error: BaseException, rollback_error: BaseException) -> NoReturn:
        if self._settings.context_error_policy == "group":
            raise_grouped_errors("lock acquisition backend and rollback both failed", acquire_error, rollback_error)
        raise_chained_errors(acquire_error, rollback_error)

    async def _rollback_failed_registration_async(self, registration_error: BaseException) -> None:
        tracking_error: BaseException | None = None
        try:
            # Rollback may fail too; retain the fd so a child can close it without another identity probe.
            self._register_unverified_context_descriptor()
        except BaseException as error:  # ruff:ignore[blind-except]  # pragma: no cover - allocation/control-flow during fallback
            tracking_error = error
        try:
            await self._undo_async_acquire()
        except BaseException as rollback_error:  # ruff:ignore[blind-except]  # preserve rollback and registration failures
            raise_cleanup_errors(
                "descriptor registration cleanup failed", registration_error, tracking_error, rollback_error
            )
        if tracking_error is not None:  # pragma: no cover - requires failed in-memory fallback
            raise_cleanup_errors("descriptor registration cleanup failed", registration_error, tracking_error)

    async def _invoke_on_acquired_async(self) -> None:
        if self._settings.on_acquired is None or self._context.lock_counter != 1:
            return
        try:
            self._settings.on_acquired(cast("int", self._context.lock_file_fd))
        except BaseException as callback_error:  # caller control-flow errors must release the lock
            callback_context = callback_error.__context__
            try:
                await self._undo_async_acquire()
            except BaseException as release_error:  # ruff:ignore[blind-except]  # both errors surface via the group below
                raise_body_and_release(callback_error, release_error)
            callback_error.__context__ = callback_context
            raise

    def _break_expired_and_acquire(self) -> None:
        # Runs as one backend call so the lifetime check's lstat and unlink stay off the event loop with the acquire.
        self._try_break_expired_lock()
        self._acquire_with_fork_tracking()

    async def _undo_async_acquire(self) -> None:
        self._mark_rollback_tried()
        await drain_future(self._start_tracked_release())

    @override
    def _mark_rollback_tried(self) -> None:
        self._async_context.rollback_tried = True

    async def _rollback_backend_cancelled_acquire(self, acquire_error: asyncio.CancelledError) -> NoReturn:
        if self.is_locked:
            try:
                await self._undo_async_acquire()
            except BaseException as rollback_error:  # ruff:ignore[blind-except]  # both backend errors must surface
                self._raise_acquire_rollback_errors(acquire_error, rollback_error)
        raise acquire_error


__all__ = [
    "AsyncAcquisition",
]
