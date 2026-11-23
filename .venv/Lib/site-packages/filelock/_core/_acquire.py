"""Synchronous lock acquisition, retries and rollback."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    assert __spec__ is not None

__lazy_modules__ = [
    "filelock._filesystem",
    "secrets",
    "threading",
    f"{__spec__.parent}._errors",
    f"{__spec__.parent}._fork",
    f"{__spec__.parent}._registry",
    f"{__spec__.parent}._shutdown",
    f"{__spec__.parent}._state",
]

import contextlib
import logging
import os
import secrets
import sys
import time
from abc import abstractmethod
from threading import current_thread
from typing import Final, Generic, TypeVar, cast

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Hashable
    from types import TracebackType
    from typing import Literal

    from filelock import BaseFileLock, ReadWriteLock, SoftReadWriteLock
from filelock._filesystem import ensure_directory_exists

from ._errors import Timeout, raise_body_and_release, raise_cleanup_errors
from ._fork import ensure_current_process, fork_transition
from ._registry import REGISTRY, canonical, path_key
from ._release import LockRelease
from ._shutdown import LIVE_LOCKS
from ._state import AcquireWait, FileLockContext, on_this_stack

_LOGGER: Final[logging.Logger] = logging.getLogger("filelock")
_LockT = TypeVar("_LockT", bound="BaseFileLock | ReadWriteLock | SoftReadWriteLock")


class LockAcquisition(LockRelease):
    def _check_acquisition_state(self, state: FileLockContext) -> None:
        # A handler cannot wait for the acquire it interrupted.
        if not self.is_locked and any(on_this_stack(each.frame) for each in state.in_flight):
            msg = f"Deadlock: lock '{self.lock_file}' is acquired again while this thread's acquire of it waits"
            raise RuntimeError(msg)
        # The kernel may already have dropped a hold whose release was interrupted.
        if on_this_stack(state.releasing):
            msg = f"lock '{self.lock_file}' is acquired again while this thread's release of it runs"
            raise RuntimeError(msg)
        if self.is_locked:
            self._raise_if_hold_unusable()

    def _raise_if_hold_unusable(self) -> None:
        if self._context.unlock_uncertain:  # pragma: win32 no cover
            msg = f"lock '{self.lock_file}' may have been released; call release() again before acquiring it"
            raise RuntimeError(msg)

    @contextlib.contextmanager
    def _transition_admission(self, wait: AcquireWait) -> Generator[None]:
        # Shared instances serialize transitions. Polling the gate preserves cancellation and the deadline.
        if self._settings.thread_local:
            yield
            return
        deadline = None if wait.timeout < 0 else wait.start_time + wait.timeout
        interval = wait.poll_interval if wait.blocking else 0.0
        # interval leads min() so a nonblocking acquire with a NaN timeout waits zero seconds.
        while not self._transition_lock.acquire(
            timeout=interval if deadline is None else min(interval, max(deadline - time.perf_counter(), 0.0))
        ):
            if not wait.blocking or (wait.cancel_check is not None and wait.cancel_check()):
                raise Timeout(self.lock_file)
            if deadline is not None and time.perf_counter() >= deadline:
                raise Timeout(self.lock_file)
        try:
            yield
        finally:
            self._transition_lock.release()

    def _resolve_lock_path(self) -> str:
        resolved = canonical(self.lock_file)
        if self._singleton_shared and not self.is_locked and path_key(resolved) != self._singleton_key:
            msg = f"singleton lock path changed after sharing: {self.lock_file}"
            raise RuntimeError(msg)
        return resolved

    def _acquire_level(
        self, state: FileLockContext, levels_before: int, canonical_path: str, wait: AcquireWait
    ) -> None:
        state.in_flight[-1].levels_before = levels_before
        state.lock_counter = levels_before + 1
        self._raise_if_would_deadlock(canonical_path, timeout=wait.timeout, blocking=wait.blocking)
        if not self.is_locked:
            self._pin_lock_path(canonical_path)
        self._poll_until_acquired(wait)
        self._commit_acquire(canonical_path)
        self._raise_if_voided()

    def _raise_if_would_deadlock(self, canonical: str, *, timeout: float, blocking: bool) -> None:
        # A handler holding another instance cannot wait for its own release.
        would_block = self._context.lock_counter == 1 and not self.is_locked and timeout < 0 and blocking
        if would_block and (holder := REGISTRY.held.get(self._registry_key(canonical))) not in {None, self._holder_id}:
            if sys.platform == "win32" and (owner := LIVE_LOCKS.get(holder)) is not None:  # pragma: win32 cover
                state = owner._hold_state()  # ruff:ignore[private-member-access]  # the registry resolves the other hold
                if (pending := state.strict_release) is not None and (
                    state.lock_file_fd is None
                    or (
                        not pending.done()
                        and pending.worker is not current_thread()
                        and not on_this_stack(state.releasing)
                    )
                ):
                    # A failed worker leaves the registry entry for an explicit retry.
                    return
            msg = (
                f"Deadlock: lock '{self.lock_file}' is already held by a different {self._deadlock_holder_desc}. "
                f"Use is_singleton=True to enable reentrant locking across instances."
            )
            raise RuntimeError(msg)

    def _registry_key(self, canonical: str) -> Hashable:
        canonical = path_key(canonical)
        return canonical if (scope := self._deadlock_scope()) is None else (scope, canonical)

    @staticmethod
    def _deadlock_scope() -> Hashable | None:
        # Async locks scope deadlock detection to a task because several tasks can share the thread.
        return None

    def _pin_lock_path(self, canonical: str) -> None:
        # Keep the backend error for paths without a final component.
        self._context.claim_root = None if canonical.endswith(os.sep) else canonical

    def _poll_until_acquired(self, wait: AcquireWait) -> None:
        self._set_claim_deadline(wait.start_time, wait.timeout if wait.blocking else 0.0)
        lock_id = id(self)
        lock_filename = self.lock_file
        attempt = 0
        # Recreating a removed directory during a wait could split contenders across two locks.
        if not self.is_locked:
            ensure_directory_exists(self._lock_path)
        while True:
            self._raise_if_inherited()
            self._raise_if_voided()
            if not self.is_locked:
                self._try_break_expired_lock()
                _LOGGER.debug("Attempting to acquire lock %s on %s", lock_id, lock_filename)
                self._context.lock_generation += 1
                self._acquire_with_fork_tracking()
                self._raise_if_inherited()
                self._raise_if_voided()
            if self.is_locked:
                _LOGGER.debug("Lock %s acquired on %s", lock_id, lock_filename)
                return
            self._raise_if_would_deadlock(self._lock_path, timeout=wait.timeout, blocking=wait.blocking)
            if self._check_give_up(
                blocking=wait.blocking,
                cancel_check=wait.cancel_check,
                timeout=wait.timeout,
                start_time=wait.start_time,
            ):
                raise Timeout(lock_filename, self._unprobeable_holder())
            attempt += 1
            delay = self._poll_delay(wait.poll_interval, attempt)
            if wait.timeout >= 0:
                delay = min(delay, max(wait.start_time + wait.timeout - time.perf_counter(), 0.0))
            _LOGGER.debug("Lock %s not acquired on %s, waiting %s seconds ...", lock_id, lock_filename, delay)
            time.sleep(delay)

    def _raise_if_inherited(self) -> None:
        ensure_current_process()
        if self._creator_pid != os.getpid():  # pragma: forked child
            msg = f"{type(self).__name__} on {self.lock_file} was inherited across fork; construct a new instance"
            raise RuntimeError(msg)

    def _try_break_expired_lock(self) -> None:
        # Only existence locks reclaim expired markers.
        ...

    def _acquire_with_fork_tracking(self) -> None:
        with fork_transition(self):
            try:
                self._acquire()
            except BaseException as acquisition_error:
                self._rollback_failed_acquire(acquisition_error)
                raise
            try:
                self._register_context_descriptor()
            except BaseException as registration_error:  # pragma: needs fork
                self._rollback_failed_registration(registration_error)
                raise
        if self.is_locked:
            self._invoke_on_acquired()

    @abstractmethod
    def _acquire(self) -> None:
        raise NotImplementedError

    def _rollback_failed_acquire(self, acquisition_error: BaseException) -> None:
        if not self.is_locked:
            return
        self._mark_rollback_tried()
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
            self._release_with_fork_tracking()
        except BaseException as rollback_error:  # ruff:ignore[blind-except]  # preserve rollback and acquisition failures
            raise_cleanup_errors(
                "lock acquisition cleanup failed",
                acquisition_error,
                registration_error,
                tracking_error,
                rollback_error,
            )
        if registration_error is not None:  # pragma: needs fork
            raise_cleanup_errors(
                "lock acquisition cleanup failed", acquisition_error, registration_error, tracking_error
            )

    def _mark_rollback_tried(self) -> None:
        if in_flight := self._context.in_flight:
            in_flight[-1].rolled_back = True

    def _rollback_failed_registration(self, registration_error: BaseException) -> None:  # pragma: needs fork
        self._mark_rollback_tried()
        tracking_error: BaseException | None = None
        try:
            # Rollback may fail too; retain the fd so a child can close it without another identity probe.
            self._register_unverified_context_descriptor()
        except BaseException as error:  # ruff:ignore[blind-except]  # pragma: no cover - allocation/control-flow during fallback
            tracking_error = error
        try:
            self._release_with_fork_tracking()
        except BaseException as rollback_error:  # ruff:ignore[blind-except]  # preserve rollback and registration failures
            raise_cleanup_errors(
                "descriptor registration cleanup failed", registration_error, tracking_error, rollback_error
            )
        if tracking_error is not None:  # pragma: no cover - requires failed in-memory fallback
            raise_cleanup_errors("descriptor registration cleanup failed", registration_error, tracking_error)

    def _invoke_on_acquired(self) -> None:
        # Async callbacks must run on the same executor thread as the backend.
        if self._settings.on_acquired is None or self._context.lock_counter != 1:
            return
        try:
            self._settings.on_acquired(cast("int", self._context.lock_file_fd))
        except BaseException as callback_error:  # arbitrary caller code; roll back on any failure
            if not self.is_locked or any(each.rolled_back for each in self._context.in_flight):
                raise
            self._mark_rollback_tried()
            callback_context = callback_error.__context__
            try:
                self._release_with_fork_tracking()
            except BaseException as release_error:  # ruff:ignore[blind-except]  # both errors surface via the group below
                raise_body_and_release(callback_error, release_error)
            callback_error.__context__ = callback_context
            raise

    def _check_give_up(
        self,
        *,
        blocking: bool,
        cancel_check: Callable[[], bool] | None,
        timeout: float,
        start_time: float,
    ) -> bool:
        lock_id, lock_filename = id(self), self.lock_file
        if blocking is False:
            _LOGGER.debug("Failed to immediately acquire lock %s on %s", lock_id, lock_filename)
            return True
        if cancel_check is not None and cancel_check():
            _LOGGER.debug("Cancellation requested for lock %s on %s", lock_id, lock_filename)
            return True
        if 0 <= timeout <= time.perf_counter() - start_time:
            _LOGGER.debug("Timeout on acquiring lock %s on %s", lock_id, lock_filename)
            return True
        return False

    def _unprobeable_holder(self) -> str | None:  # ruff:ignore[no-self-use]  # existence locks override it
        return None

    def _poll_delay(self, poll_interval: float, attempt: int) -> float:
        # Jitter keeps contenders publishing several files from colliding on every retry.
        if not self._poll_backoff_cap:
            return poll_interval
        # Bounding the exponent avoids float overflow after many retries.
        max_backoff_exponent = 20  # pragma: needs hard-link
        window = min(
            self._poll_backoff_cap, poll_interval * 2 ** min(attempt, max_backoff_exponent)
        )  # pragma: needs hard-link
        return max(poll_interval, secrets.randbelow(int(window * 1_000_000) + 1) / 1_000_000)  # pragma: needs hard-link

    def _commit_acquire(self, canonical: str) -> None:
        # An on_acquired hook can nest before the first acquire registers the hold.
        if self._context.lock_file_registry is None:
            key = self._registry_key(canonical)
            self._context.lock_file_key = key
            # A cross-thread release needs the acquiring thread's registry.
            registry = REGISTRY.held
            self._context.lock_file_registry = registry
            registry[key] = self._holder_id

    def _raise_if_voided(self) -> None:
        if (in_flight := self._context.in_flight) and in_flight[-1].voided:
            msg = f"lock '{self.lock_file}' was force-released while this thread acquired it"
            raise RuntimeError(msg)

    def _undo_in_flight_acquire(self, canonical: str, depth: int, previous: int | None, error: BaseException) -> None:
        record = self._context.in_flight[depth] if len(self._context.in_flight) > depth else None
        if previous is None:
            return
        if record is not None and record.voided:
            previous = 0
        try:
            if not previous and (record is None or not record.rolled_back):
                self._rollback_failed_acquire(error)
        finally:
            self._reconcile_failed_acquire(canonical, levels_before=previous)

    def _reconcile_failed_acquire(self, canonical: str, *, levels_before: int) -> None:
        # Keep the registry entry while a failed rollback leaves the native lock held.
        if not self.is_locked:
            self._commit_release()
        elif levels_before:
            self._context.lock_counter = levels_before
        elif (registry := self._context.lock_file_registry) is None:
            self._commit_acquire(canonical)
        else:
            registry.setdefault(self._context.lock_file_key, self._holder_id)


class ReadWriteBackend:
    __slots__ = ()

    lock_file: str
    timeout: float
    blocking: bool

    def _acquire_level_of(
        self,
        holder: int,
        mode: Literal["read", "write"],
        timeout: float,
        *,
        blocking: bool,
        cancel_check: Callable[[], bool],
    ) -> AcquireReturnProxy:
        # Executor threads can serve multiple task owners.
        return self._acquire(mode, timeout, blocking=blocking, holder=holder, cancel_check=cancel_check)

    @abstractmethod
    def _acquire(
        self,
        mode: Literal["read", "write"],
        timeout: float,
        *,
        blocking: bool,
        holder: int,
        cancel_check: Callable[[], bool],
    ) -> AcquireReturnProxy: ...

    @abstractmethod
    def _release_level_of(self, holder: int, /) -> None: ...

    @abstractmethod
    def _holds_level_of(self, holder: int, /) -> bool: ...

    @abstractmethod
    def close(self) -> None: ...


class AcquireReturnProxy(Generic[_LockT]):
    """
    A context-aware object that will release the lock file when exiting.

    :param lock: the lock to release on exit
    """

    def __init__(self, lock: _LockT) -> None:
        self.lock: _LockT = lock

    def __enter__(self) -> _LockT:
        return self.lock

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        # The explicit union lets the type checker narrow both branches.
        lock: Final[BaseFileLock | ReadWriteLock | SoftReadWriteLock] = self.lock
        if isinstance(lock, LockRelease):
            lock._release_in_context(exc_value)  # ruff:ignore[private-member-access]  # forwards __exit__ to the owned lock's context release
        else:  # a reader/writer lock does not carry a context_error_policy
            lock.release()


__all__ = [
    "AcquireReturnProxy",
    "LockAcquisition",
    "ReadWriteBackend",
]
