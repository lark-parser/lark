"""Per-instance and thread-local state for lock operations."""

from __future__ import annotations

__lazy_modules__ = ["inspect", "operator", "warnings"]

import inspect
import os
import time
import warnings
from abc import ABC
from dataclasses import dataclass, field, fields
from operator import attrgetter
from threading import RLock, Thread, current_thread, local
from typing import TYPE_CHECKING, Final, NamedTuple

from ._fork import (
    HAS_REGISTER_AT_FORK,
    ForkClassResettable,
    ForkDescriptorOwner,
    ForkResettable,
    ensure_current_process,
    fork_transition,
    record_owned_descriptor,
    register_owned_descriptor,
    unregister_owned_descriptor,
)
from ._settings import (
    UNSET_FILE_MODE,
    LockSettings,
    check_blocking,
    override,
    resolve_poll_interval,
    resolve_timeout,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Hashable
    from concurrent.futures import Future
    from contextlib import ExitStack
    from types import FrameType

    from filelock._soft import LeaseClaim, StrictRelease


@dataclass(eq=False, slots=True, kw_only=True)  # simplint: ignore[dataclass-frozen]  # release records its outcome here
class InFlight:
    """
    One acquisition that may need to be rolled back after an interrupt.

    :param frame: frame performing the acquisition
    :param levels_before: hold count before this acquisition, once known
    :param voided: a release discarded this acquisition's hold
    :param rolled_back: cleanup already reversed this acquisition
    """

    frame: FrameType
    levels_before: int | None = None
    voided: bool = False
    rolled_back: bool = False


@dataclass  # simplint: ignore[dataclass-slots, dataclass-kw-only]  # base rejects slots; signature is public
class FileLockContext:  # simplint: ignore[too-many-attributes]  # its fields are public API
    """
    Settings and ownership state for an exclusive lock.

    :param lock_file: filesystem path used for locking
    :param timeout: default wait in seconds
    :param mode: permissions requested for a newly created lock file
    :param blocking: whether to wait on contention
    :param poll_interval: seconds between attempts
    :param lifetime: optional age in seconds at which a stale lock becomes reclaimable
    :param lock_file_fd: descriptor held by the current owner
    :param lock_file_fd_token: registration used to clean up the descriptor after a fork
    :param lock_file_fd_identity: device and inode of the held descriptor
    :param pending_lock_file_fd: descriptor opened before acquisition commits
    :param pending_lock_file_fd_identity: device and inode of the pending descriptor
    :param lock_counter: number of nested holds
    :param lock_file_key: key identifying the held lock in its owner's registry
    :param lock_file_registry: acquiring thread's registry, retained for cross-thread release
    :param owner_claim_paths: published paths for this owner's strict-lock claims
    :param claim_deadline: monotonic deadline for acquiring or withdrawing strict claims
    :param claim_withdrawal: pending withdrawal of strict-lock claims and its outcome
    :param strict_release: completion of a deferred strict-lock release
    :param claim_descriptors: descriptors keyed by strict-lock claim path
    :param claim_protection: resources retained to protect published strict-lock claims
    :param releasing: frame currently releasing the lock
    :param acquiring: frame currently acquiring the lock
    :param claim_root: resolved lock path used during this acquisition or hold
    :param lease_claim: token, refresh thread and compromise state of a renewable lease
    :param lock_generation: generation used to distinguish successive holds
    :param in_flight: acquisition frames that may still need rollback
    :param unlock_uncertain: whether an interrupted release may have unlocked the descriptor
    :ivar soft_fallback: whether the Unix backend uses a soft marker for this path
    """

    lock_file: str
    timeout: float
    mode: int
    blocking: bool
    poll_interval: float
    lifetime: float | None = None
    soft_fallback: bool = field(default=False, init=False)
    lock_file_fd: int | None = None
    lock_file_fd_token: int | None = None
    lock_file_fd_identity: tuple[int, int] | None = None
    pending_lock_file_fd: int | None = None
    pending_lock_file_fd_identity: tuple[int, int] | None = None
    lock_counter: int = 0
    lock_file_key: Hashable | None = None
    # A different thread can release a shared lock. It needs the acquiring thread's registry.
    lock_file_registry: dict[Hashable, int] | None = None
    owner_claim_paths: tuple[str, ...] = ()
    claim_deadline: float | None = None
    claim_withdrawal: Future[tuple[list[str], list[BaseException]]] | None = None
    strict_release: StrictRelease | None = None
    claim_descriptors: dict[str, int] | None = None
    claim_protection: ExitStack[bool | None] | None = None
    # A signal handler must not release a descriptor its interrupted frame already closed.
    releasing: FrameType | None = None
    acquiring: FrameType | None = None
    # A directory change during a wait or hold must not redirect the release.
    claim_root: str | None = None
    lease_claim: LeaseClaim | None = None
    lock_generation: int = field(default=0, kw_only=True)
    in_flight: list[InFlight] = field(default_factory=list, kw_only=True, repr=False)
    unlock_uncertain: bool = field(default=False, kw_only=True)

    def acquire_wait(
        self,
        timeout: float | None,
        poll_interval: float | None,
        poll_intervall: float | None,
        *,
        blocking: bool | None,
        cancel_check: Callable[[], bool] | None,
    ) -> AcquireWait:
        """
        Resolve per-call overrides against this context's settings.

        :param timeout: wait limit in seconds, or None for the context default
        :param poll_interval: seconds between attempts, or None for the context default
        :param poll_intervall: deprecated spelling that overrides poll_interval when supplied
        :param blocking: whether to wait, or None for the context default
        :param cancel_check: optional callback that ends the wait when it returns true
        :returns: resolved wait settings and their monotonic start time
        :raises TypeError: a setting has the wrong type
        :raises ValueError: a blocking timeout is NaN or the polling interval is out of range
        """
        timeout = self.timeout if timeout is None else timeout
        blocking = self.blocking if blocking is None else blocking

        check_blocking(blocking)

        if poll_intervall is not None:
            warnings.warn("use poll_interval instead of poll_intervall", DeprecationWarning, stacklevel=3)
            poll_interval = poll_intervall

        poll_interval = poll_interval if poll_interval is not None else self.poll_interval
        poll_interval = resolve_poll_interval(poll_interval)
        timeout = resolve_timeout(timeout, blocking=blocking)

        return AcquireWait(blocking, cancel_check, timeout, poll_interval, time.perf_counter())


class AcquireWait(NamedTuple):
    """
    Resolved settings for one acquisition attempt.

    :param blocking: whether contention permits another attempt
    :param cancel_check: optional callback that ends a pending wait when it returns true
    :param timeout: wait limit in seconds, or a negative value for no limit
    :param poll_interval: seconds between attempts
    :param start_time: reading from :func:`time.perf_counter` when the wait began
    """

    blocking: bool
    cancel_check: Callable[[], bool] | None
    timeout: float
    poll_interval: float
    start_time: float


class ThreadLocalFileContext(FileLockContext, local):
    current: FileLockContext

    # threading.local runs __init__ again with these arguments the first time each thread touches the context.
    def __init__(  # ruff:ignore[too-many-arguments]  # mirrors the FileLockContext fields set at construction
        self,
        *,
        lock_file: str,
        timeout: float,
        mode: int,
        blocking: bool,
        poll_interval: float,
        lifetime: float | None = None,
    ) -> None:
        self.current = FileLockContext(
            lock_file=lock_file,
            timeout=timeout,
            mode=mode,
            blocking=blocking,
            poll_interval=poll_interval,
            lifetime=lifetime,
        )


def delegate_to_current(name: str) -> property:
    return property(
        attrgetter(f"current.{name}"),
        lambda context, value: setattr(context.current, name, value),
    )


for _field in fields(FileLockContext):
    setattr(ThreadLocalFileContext, _field.name, delegate_to_current(_field.name))


class LockState(ForkResettable, ForkDescriptorOwner, ForkClassResettable, ABC):
    _lifetime_supported: bool = False
    _lifetime_replacements: tuple[str, str] | None = None
    _lifetime_unsupported_reason: str = "a native OS lock cannot be broken safely by file age"
    _context: FileLockContext
    _settings: LockSettings
    _creator_pid: int
    _holder_id: int
    _transition_lock: RLock
    _thread_holds: dict[int, tuple[FileLockContext, Thread]]
    _thread_pending: dict[int, tuple[FileLockContext, Thread]]
    _flockless_roots: frozenset[str]
    _singleton_key: str | None = None
    _singleton_shared: bool = False
    _poll_backoff_cap: float = 0.0
    _deadlock_holder_desc: str = "FileLock instance in this thread"

    @property
    def is_locked(self) -> bool:
        """
        Whether this instance still records a hold. After a native unlock raises, this can remain ``True`` until an
        explicit ``release()`` retry, even if the kernel already released the lock.

        .. versionchanged:: 2.0.0

            This was previously a method and is now a property.

        """
        ensure_current_process()
        return self._context.lock_file_fd is not None

    @property
    def _lock_path(self) -> str:
        # Pinning prevents a directory change from redirecting an acquire or its matching release.
        return self._context.claim_root or self.lock_file

    @property
    def lock_file(self) -> str:
        """Path to the lock file."""
        return self._context.lock_file

    @property
    def lock_counter(self) -> int:
        """The number of times this lock has been acquired (but not yet released)."""
        ensure_current_process()
        return self._context.lock_counter

    def _set_claim_deadline(self, start_time: float, timeout: float) -> None:
        self._context.claim_deadline = None if timeout < 0 else start_time + timeout

    def _register_unverified_context_descriptor(self) -> None:
        if (
            self._context.lock_file_fd is not None and self._context.lock_file_fd_token is None
        ):  # pragma: no branch  # only an untracked descriptor needs registration
            if not HAS_REGISTER_AT_FORK:  # pragma: lacks fork
                return
            with fork_transition():  # pragma: needs fork
                self._context.lock_file_fd_token = record_owned_descriptor(self._context.lock_file_fd, None)

    def _unregister_released_descriptor(self) -> None:
        if self._context.lock_file_fd is None:
            if (token := self._context.lock_file_fd_token) is not None:  # pragma: needs fork
                unregister_owned_descriptor(token)
            self._context.lock_file_fd_token = None
            self._context.lock_file_fd_identity = None

    def _register_context_descriptor(self) -> None:
        if self._context.lock_file_fd is not None and self._context.lock_file_fd_token is None:
            self._context.lock_file_fd_token = register_owned_descriptor(
                self._context.lock_file_fd,
                self._context.lock_file_fd_identity,
            )

    def is_thread_local(self) -> bool:
        """:returns: a flag indicating if this lock is thread local or not"""
        return self._settings.thread_local

    def _close_released_fd(self, fd: int, *, default_suppresses: bool) -> None:
        # Retrying close after EINTR could close a reused descriptor.
        try:
            os.close(fd)
        except OSError:
            if not self._suppresses_close_error(default_suppresses=default_suppresses):
                raise

    def _suppresses_close_error(self, *, default_suppresses: bool) -> bool:
        return self._settings.close_error_policy == "suppress" or (
            self._settings.close_error_policy == "default" and default_suppresses
        )

    def _open_mode(self) -> int:
        # The filesystem applies umask and default ACLs when no mode was specified.
        return 0o666 if self._context.mode == UNSET_FILE_MODE else self._context.mode

    def _mark_descriptor_owned(self, fd: int, identity: tuple[int, int] | None = None) -> None:
        state: Final[FileLockContext] = self._hold_state()
        # Held first, pending cleared second: an interrupt between the two then leaves the descriptor recorded.
        state.lock_file_fd = fd
        state.unlock_uncertain = False
        state.lock_file_fd_identity = identity
        state.pending_lock_file_fd = None
        state.pending_lock_file_fd_identity = None
        if isinstance(self._context, ThreadLocalFileContext):
            self._thread_pending.pop(id(state), None)
            self._thread_holds[id(state)] = state, current_thread()

    def _hold_state(self) -> FileLockContext:
        return self._context.current if isinstance(self._context, ThreadLocalFileContext) else self._context

    def _mark_descriptor_pending(self, fd: int, identity: tuple[int, int] | None = None) -> None:
        state: Final[FileLockContext] = self._hold_state()
        state.pending_lock_file_fd = fd
        state.pending_lock_file_fd_identity = identity
        if isinstance(self._context, ThreadLocalFileContext):
            self._thread_pending[id(state)] = state, current_thread()

    def _mark_descriptor_released(self) -> None:
        state: Final[FileLockContext] = self._hold_state()
        state.pending_lock_file_fd = None
        state.pending_lock_file_fd_identity = None
        state.lock_file_fd = None
        state.unlock_uncertain = False
        state.lock_file_fd_identity = None
        if isinstance(self._context, ThreadLocalFileContext):
            self._thread_pending.pop(id(state), None)
            if state.strict_release is not None:  # pragma: win32 cover
                return
            self._thread_holds.pop(id(state), None)

    @override
    def _reset_after_fork_in_child(self) -> None:  # pragma: forked child
        # Discard parent state even when a PID namespace gives the child the same numeric PID.
        self._transition_lock = RLock()
        self._creator_pid = -1
        if isinstance(self._context, ThreadLocalFileContext):
            self._thread_holds.clear()
            self._thread_pending.clear()
        self._context.soft_fallback = False
        self._flockless_roots = frozenset()
        self._context.owner_claim_paths = ()
        self._context.claim_protection = None
        self._context.claim_root = None
        self._context.lock_file_fd = None
        self._context.unlock_uncertain = False
        self._context.lock_file_fd_token = None
        self._context.lock_file_fd_identity = None
        self._context.pending_lock_file_fd = None
        self._context.pending_lock_file_fd_identity = None
        self._context.lock_counter = 0
        self._context.releasing = None
        # The forking thread's own acquire continues in the child and removes its record when it ends.
        self._context.in_flight = [each for each in self._context.in_flight if on_this_stack(each.frame)]
        self._context.acquiring = self._context.in_flight[-1].frame if self._context.in_flight else None
        self._context.lock_file_key = None
        self._context.lock_file_registry = None
        self._context.lease_claim = None

    @override
    def _descriptors_for_fork(self) -> tuple[tuple[int, tuple[int, int] | None], ...]:  # pragma: needs fork
        descriptors: list[tuple[int, tuple[int, int] | None]] = []
        if self._context.lock_file_fd is not None and self._context.lock_file_fd_token is None:
            descriptors.append((self._context.lock_file_fd, self._context.lock_file_fd_identity))
        if self._context.pending_lock_file_fd is not None:
            descriptors.append((self._context.pending_lock_file_fd, self._context.pending_lock_file_fd_identity))
        return tuple(descriptors)


def on_this_stack(frame: FrameType | None) -> bool:
    if frame is None:
        return False
    caller = inspect.currentframe()
    while caller is not None and caller is not frame:
        caller = caller.f_back
    return caller is not None


__all__ = [
    "AcquireWait",
    "FileLockContext",
    "InFlight",
    "LockState",
    "ThreadLocalFileContext",
    "delegate_to_current",
    "on_this_stack",
]
