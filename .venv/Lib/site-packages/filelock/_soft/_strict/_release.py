"""Strict soft-lock release and pending cleanup after a release deadline."""

from __future__ import annotations

__lazy_modules__ = ["functools", "inspect", "threading"]

import contextlib
import functools
import inspect
import sys
import time
from concurrent.futures import Future
from threading import TIMEOUT_MAX, RLock, Thread
from typing import TYPE_CHECKING

from filelock._core import (
    BaseFileLock,
    ReleasePendingError,
    ThreadLocalFileContext,
    Timeout,
    on_this_stack,
    override,
    seconds,
)

if sys.platform == "win32":  # pragma: win32 cover
    from threading import current_thread, main_thread


if TYPE_CHECKING:
    from collections.abc import Generator

    from filelock._core import AcquireWait, FileLockContext


class TimedReleaseLock(BaseFileLock):
    _finalizing = False
    _timed_release_supported = True

    def release_with_timeout(self, timeout: float) -> None:
        """
        Release one acquisition. On Windows, limit how long the caller waits for the final release.

        POSIX releases synchronously. On Windows, call :meth:`~filelock.ReleasePendingError.wait` to await a
        pending release. Retry on the original instance if withdrawal fails and the lock remains held.

        :param timeout: maximum time in seconds to wait on Windows
        :raises ReleasePendingError: release started on Windows and is still running at the deadline
        :raises TimeoutError: a concurrent transition prevented release from starting on Windows by the deadline
        :raises NotImplementedError: called on an asynchronous strict lock
        """
        if not self._timed_release_supported:
            msg = "release_with_timeout requires a synchronous strict lock"
            raise NotImplementedError(msg)
        timeout = _release_timeout(timeout)
        if sys.platform == "win32":  # pragma: win32 cover
            self._release_with_timeout(timeout)
        else:
            self.release()  # pragma: win32 no cover

    def _release_with_timeout(self, timeout: float) -> None:  # pragma: win32 cover
        self._raise_if_inherited()
        deadline = time.perf_counter() + timeout
        state = self._hold_state()
        if (
            ((active := state.strict_release) is not None and active.worker is current_thread())
            or on_this_stack(state.releasing)
            or any(on_this_stack(each.frame) for each in state.in_flight)
        ):
            msg = "cannot start a timed release during this thread's lock transition"
            raise RuntimeError(msg)
        # A worker clears the descriptor before it reports whether close succeeded.
        held = state.lock_file_fd is not None
        pending = state.strict_release
        if pending is None and held:
            if not self._transition_lock.acquire(timeout=max(0, deadline - time.perf_counter())):
                msg = f"timed out waiting to start release of {self.lock_file!r}"
                raise TimeoutError(msg)
            try:
                pending = state.strict_release
                if pending is None and state.lock_file_fd is not None:
                    if state.lock_counter > 1:
                        state.lock_counter -= 1
                        return
                    pending = self._start_timed_release(state)
            finally:
                self._transition_lock.release()
        if pending is not None:
            self._observe_release(state, pending, max(0, deadline - time.perf_counter()))
        elif state.lock_file_registry is not None:
            self._finish_interrupted_release()

    def _start_timed_release(self, state: FileLockContext) -> StrictRelease:  # pragma: win32 cover
        pending = StrictRelease()

        def withdraw() -> None:
            with pending.guard:
                if pending.done():
                    return
            try:
                if isinstance(self._context, ThreadLocalFileContext):
                    self._context.current = state
                # An observer can hold the shared transition gate while it waits for this result.
                self._release_from_worker(state)
            except BaseException as error:  # ruff: ignore[blind-except]  # propagate worker failures to the waiting owner
                pending.set_exception(error)
            else:
                self._thread_holds.pop(id(state), None)
                pending.set_result(None)

        worker = Thread(target=withdraw, name="filelock-strict-release", daemon=True)
        with pending.guard:
            state.releasing = inspect.currentframe()
            try:
                pending.worker = worker
                state.strict_release = pending
                worker.start()
            except BaseException as error:  # a signal can arrive after the thread started
                state.strict_release = None
                pending.set_exception(error)
                raise
            finally:
                state.releasing = None
        return pending

    if sys.platform == "win32":  # pragma: win32 cover

        @property
        @override
        def is_locked(self) -> bool:
            """Whether this hold owns a lock or still has a release running."""
            return super().is_locked or ((pending := self._context.strict_release) is not None and not pending.done())

        @contextlib.contextmanager
        @override
        def _transition_admission(self, wait: AcquireWait) -> Generator[None]:
            state = self._hold_state()
            if (active := state.strict_release) is not None and (
                active.worker is current_thread() or on_this_stack(state.releasing)
            ):
                msg = "cannot acquire during this thread's release"
                raise RuntimeError(msg)
            with super()._transition_admission(wait):
                if (pending := state.strict_release) is not None:
                    deadline = None if wait.timeout < 0 else wait.start_time + wait.timeout
                    while not pending.done():
                        if self._check_give_up(
                            blocking=wait.blocking,
                            cancel_check=wait.cancel_check,
                            timeout=wait.timeout,
                            start_time=wait.start_time,
                        ):
                            raise Timeout(state.lock_file)
                        interval = (
                            wait.poll_interval
                            if deadline is None
                            else min(deadline - time.perf_counter(), wait.poll_interval)
                        )
                        with contextlib.suppress(TimeoutError):
                            pending.exception(max(0, interval))
                    if state.lock_file_fd is not None:
                        msg = "the previous release left the claim held; retry release before acquiring"
                        raise RuntimeError(msg)
                    self._forget_release(state, pending)
                yield

        @override
        def _release_current(self, *, force: bool) -> None:
            state = self._hold_state()
            held = state.lock_file_fd is not None
            # Waiting for the worker does not need the gate another observer may hold.
            with (
                self._transition_lock
                if held and not self.is_thread_local() and state.strict_release is None
                else contextlib.nullcontext()
            ):
                if (pending := state.strict_release) is None:
                    if held:
                        super()._release_current(force=force)
                    elif state.lock_file_registry is not None:
                        self._finish_interrupted_release()
                    return
            if not self._finalizing or pending.done():
                self._observe_release(state, pending, None)

    def _forget_release(self, state: FileLockContext, pending: StrictRelease) -> None:  # pragma: win32 cover
        with pending.guard:
            if state.strict_release is pending:
                if isinstance(self._context, ThreadLocalFileContext) and state.lock_file_fd is None:
                    self._thread_holds.pop(id(state), None)
                state.strict_release = None

    def _observe_release(
        self, state: FileLockContext, pending: StrictRelease, timeout: float | None
    ) -> None:  # pragma: win32 cover
        if not pending.done() and pending.worker is current_thread():
            msg = "a release worker cannot wait for its own completion"
            raise RuntimeError(msg)
        deadline = None if timeout is None else time.perf_counter() + _release_timeout(timeout)
        signal_interval = 0.1
        while True:
            wait = None if deadline is None else max(0, deadline - time.perf_counter())
            # Older Windows interpreters dispatch signals only after the condition wait returns.
            if current_thread() is main_thread() and (wait is None or wait > signal_interval):
                wait = signal_interval
            try:
                error = pending.exception(wait)
            except TimeoutError:
                if deadline is not None and time.perf_counter() >= deadline:
                    msg = f"release of {state.lock_file!r} is still pending"
                    raise ReleasePendingError(msg, functools.partial(self._observe_release, state, pending)) from None
            else:
                break
        self._forget_release(state, pending)
        if error is not None:
            raise error


def _release_timeout(value: float) -> float:
    if not 0 <= (timeout := seconds("timeout", value)) <= TIMEOUT_MAX:
        msg = f"timeout must be between 0 and {TIMEOUT_MAX} seconds"
        raise ValueError(msg)
    return timeout


class StrictRelease(Future[None]):
    """
    Future for a strict lock release that may finish after its deadline on Windows.

    :ivar guard: mutex protecting the start and completion of this release
    :ivar worker: thread performing the release, or None before it starts
    """

    guard: RLock
    worker: Thread | None

    def __init__(self) -> None:  # pragma: win32 cover
        super().__init__()
        self.guard = RLock()
        self.worker = None


__all__ = [
    "StrictRelease",
    "TimedReleaseLock",
]
