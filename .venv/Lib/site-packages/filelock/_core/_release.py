"""Synchronous lock release and context manager exit."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    assert __spec__ is not None

__lazy_modules__ = [
    "contextlib",
    "inspect",
    "threading",
    f"{__spec__.parent}._errors",
    f"{__spec__.parent}._fork",
    f"{__spec__.parent}._registry",
]

import contextlib
import inspect
import logging
import os
from abc import abstractmethod
from threading import current_thread, main_thread
from typing import Final

if TYPE_CHECKING:
    from types import TracebackType
from ._errors import is_system_call_failure, raise_body_and_release
from ._fork import ensure_current_process, fork_transition
from ._registry import REGISTRY
from ._state import FileLockContext, LockState, ThreadLocalFileContext, on_this_stack

_LOGGER: Final[logging.Logger] = logging.getLogger("filelock")


class LockRelease(LockState):
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._release_in_context(exc_value)

    def _release_in_context(self, body_error: BaseException | None) -> None:
        try:
            self.release()
        except BaseException as release_error:
            if body_error is None or self._settings.context_error_policy == "chain":
                raise
            raise_body_and_release(body_error, release_error)

    def release(self, force: bool = False) -> None:  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # public API: positional bool kept for backwards compatibility
        """
        Release one acquisition. The final release unlocks the file and may remove its pathname.

        :param force: release every level held by the caller, including holds left by exited workers on a
            thread-local lock. The main thread and running workers keep their own holds.

        Dropping the last reference releases all threads' holds. At interpreter exit, running daemon threads
        keep their holds, and a shared lock stays held while another thread runs.
        """
        ensure_current_process()
        if (pending := self._context.strict_release) is not None and (
            pending.worker is current_thread() or on_this_stack(self._context.releasing)
        ):  # pragma: win32 cover
            return
        release_snapshot: tuple[int, int] | None = None
        transition_entered = False
        try:  # ruff:ignore[too-many-statements-in-try-clause]  # gate-entry signals and release failures need separate recovery
            release_snapshot = (self._context.lock_generation, self._context.lock_counter)
            with (
                contextlib.nullcontext()
                if self._settings.thread_local or self._context.lock_file_fd is None or pending is not None
                else self._transition_lock
            ):
                try:
                    transition_entered = True
                    release_snapshot = (self._context.lock_generation, self._context.lock_counter)
                    self._release_current(force=force)
                except BaseException as release_error:
                    self._retry_interrupted_release(release_snapshot, release_error, force=force, transition_held=True)
                    raise
        except BaseException as release_error:
            if not transition_entered:
                self._retry_interrupted_release(release_snapshot, release_error, force=force, transition_held=False)
            raise
        if force:
            self._release_thread_holds(exited_only=True)

    def _release_current(self, *, force: bool) -> None:
        # Only a live descriptor needs the acquisition gate. An unheld lock must not wait behind a contender.
        if self._context.lock_file_fd is None:
            # An interrupt after unlock can leave a registry entry that blocks other instances.
            if self._context.lock_file_registry is not None:
                self._finish_interrupted_release()
            return
        with contextlib.nullcontext() if self._settings.thread_local else self._transition_lock:
            self._release_held(force=force)

    def _finish_interrupted_release(self) -> None:
        # A concurrent acquire takes ownership of the registry entry at commit.
        if not self._transition_lock.acquire(blocking=False):
            return  # pragma: no cover  # only a concurrent acquire of a shared instance holds the gate
        try:
            if (
                self._context.lock_file_fd is None and self._context.strict_release is None
            ):  # pragma: no branch  # a racing transition takes ownership
                self._commit_release()
        finally:
            self._transition_lock.release()

    def _commit_release(self) -> None:
        self._context.lock_counter = 0
        self._drop_registry_entry()
        self._context.claim_root = None

    def _drop_registry_entry(self) -> None:
        # A retry after an interrupt may find a peer registered under the same key.
        key, registry = self._context.lock_file_key, self._context.lock_file_registry
        if registry is not None and registry.get(key) == self._holder_id:
            del registry[key]
        self._context.lock_file_registry = None
        self._context.lock_file_key = None

    def _release_held(self, *, force: bool) -> None:
        state: Final[FileLockContext] = self._hold_state()
        # Until the releasing frame returns, another release could close a reused descriptor.
        if self._creator_pid != os.getpid() or state.lock_file_fd is None or on_this_stack(state.releasing):
            return
        record = next((each for each in reversed(state.in_flight) if on_this_stack(each.frame)), None)
        if (
            record is not None
            and not force
            and (record.levels_before is None or state.lock_counter <= record.levels_before + 1)
        ):
            msg = f"lock '{self.lock_file}' is released while this thread's acquire of it is still running"
            raise RuntimeError(msg)
        if record is not None and force:
            record.rolled_back = True
        if not force and state.lock_counter > 1 and not state.unlock_uncertain:
            state.lock_counter -= 1
            return
        state.releasing = inspect.currentframe()
        try:
            _LOGGER.debug("Attempting to release lock %s on %s", id(self), self.lock_file)
            self._release_with_fork_tracking()
        finally:
            # A backend can raise after unlocking. A live descriptor still needs an explicit release retry.
            if state.lock_file_fd is None:  # pragma: no branch  # a release that returns cleared the descriptor
                self._commit_release()
                if record is not None and force:
                    for each in state.in_flight:
                        each.voided = True
            state.releasing = None
        _LOGGER.debug("Lock %s released on %s", id(self), self.lock_file)

    def _release_with_fork_tracking(self) -> None:
        with fork_transition(self):
            try:
                self._release()
            except BaseException as release_error:
                # A backend unlocks first and clears the descriptor second. A signal handler that raises in between
                # leaves a hold the OS dropped. An errno-bearing error can also come from that handler, so only a
                # non-system-call error gets an automatic retry. An uncertain unlock needs an explicit retry.
                if self._context.lock_file_fd is not None and not is_system_call_failure(release_error):
                    with contextlib.suppress(Exception):
                        self._release()
                raise
            finally:
                self._unregister_released_descriptor()

    @abstractmethod
    def _release(self) -> None:
        raise NotImplementedError

    def _retry_interrupted_release(
        self, snapshot: tuple[int, int] | None, release_error: BaseException, *, force: bool, transition_held: bool
    ) -> None:
        # A retry can only touch the original hold; a later acquirer may restore the same recursion depth.
        if (
            snapshot is None
            or self._context.lock_file_fd is None
            or self._context.strict_release is not None
            or is_system_call_failure(release_error)
        ):
            return
        with (
            contextlib.suppress(Exception),
            contextlib.nullcontext() if transition_held or self._settings.thread_local else self._transition_lock,
        ):
            if self._context.strict_release is None and snapshot == (
                self._context.lock_generation,
                self._context.lock_counter,
            ):
                self._release_current(force=force)

    def _release_thread_holds(self, *, exited_only: bool) -> None:
        if not isinstance(context := self._context, ThreadLocalFileContext):
            return
        # Serialized, or two threads would both close an exited thread's descriptor; copy() is atomic free-threaded.
        with self._transition_lock:
            own: Final[FileLockContext] = context.current
            for held, thread in self._thread_holds.copy().values():
                # threading marks main done before atexit, while its callbacks may still use the hold.
                if exited_only and (thread.is_alive() or thread is main_thread()):
                    continue
                context.current = held
                try:
                    self._release_current(force=True)
                finally:
                    context.current = own

    def _release_from_worker(self, state: FileLockContext) -> None:  # pragma: win32 cover
        # A logging callback on the release worker cannot wait for a claim the worker still has to withdraw.
        key = state.lock_file_key
        registry = REGISTRY.held
        registry.setdefault(key, self._holder_id)
        try:
            self._release_held(force=True)
        finally:
            if registry.get(key) == self._holder_id:
                del registry[key]


__all__ = [
    "LockRelease",
]
