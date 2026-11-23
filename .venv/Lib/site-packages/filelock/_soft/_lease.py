"""Soft lock leases with heartbeat renewal and loss detection."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    assert __spec__ is not None

__lazy_modules__ = [
    "contextlib",
    "filelock._filesystem",
    "filelock._identity",
    "math",
    "pathlib",
    "secrets",
    "threading",
    "weakref",
    f"{__spec__.parent}._records",
]

import os
import pathlib
import secrets
import sys
import time
from contextlib import suppress
from dataclasses import dataclass
from math import isfinite
from threading import Event, Thread, current_thread
from typing import TYPE_CHECKING, Final, Literal
from weakref import WeakMethod

from filelock._core import LeaseSettingsMismatch, check_timeout_max, override, seconds
from filelock._filesystem import pin_inode, touch
from filelock._identity import owner_is_stale

from ._exclusive import MarkerSoftFileLock
from ._records import OwnerMode, OwnerRecord, parse_marker, read_lock_file

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from typing import Unpack

    from filelock._core import ExtraValue, LockOptions

#: A lease can lose its marker or be evicted from a read/write generation.
CompromiseReason = Literal["marker-missing", "owner-changed", "refresh-failed", "evicted"]

_RefreshOutcome = Literal["ok", "transient", "marker-missing", "owner-changed"]
_DEFAULT_LEASE_DURATION: Final[float] = 30.0


class SoftFileLease(MarkerSoftFileLock):
    """
    A marker lease refreshed by its holder. Peers may take an expired claim while the previous holder still runs.
    Use :class:`~filelock.StrictSoftFileLock` when overlap is unsafe. The claim token identifies a hold. Fencing
    requires a monotonic generation enforced by the protected resource.

    Peers measure expiry on their own monotonic clocks and must agree on ``lease_duration``. On Windows an open marker
    can prevent takeover until the holder exits.

    .. versionadded:: 3.30.0

    :param lock_file: path to the lock file
    """

    _owner_mode: OwnerMode = "lease"

    # A lease has one expiry clock, set by lease_duration.
    _lifetime_supported: bool = False
    _lifetime_unsupported_reason: str = "lease_duration sets when a lease expires"

    def __init__(
        self,
        lock_file: str | os.PathLike[str],
        *,
        lease_duration: float = _DEFAULT_LEASE_DURATION,
        heartbeat_interval: float | None = None,
        on_compromise: Callable[[LeaseCompromise], None] | None = None,
        **kwargs: Unpack[LockOptions],
    ) -> None:
        """
        Create a marker lease.

        :param lease_duration: seconds an unchanged claim must be observed before takeover. All peers must agree.
        :param heartbeat_interval: seconds between refreshes. Defaults to a third of the lease duration. Must be shorter
            than the lease duration and at most :data:`threading.TIMEOUT_MAX`.
        :param on_compromise: called by the heartbeat thread when the claim is lost. With thread-local locks, signal the
            acquiring thread to release its hold.
        :param kwargs: options accepted by :class:`~filelock.BaseFileLock`.
        """
        # A float subclass may write a repr the marker parser cannot read back.
        if not isfinite(lease_duration := seconds("lease_duration", lease_duration)) or lease_duration <= 0:
            msg = f"lease_duration must be positive and finite, got {lease_duration!r}"
            raise ValueError(msg)
        heartbeat_interval = (
            lease_duration / 3 if heartbeat_interval is None else seconds("heartbeat_interval", heartbeat_interval)
        )
        if not 0 < heartbeat_interval < lease_duration:
            msg = f"heartbeat_interval must be positive and below lease_duration, got {heartbeat_interval!r}"
            raise ValueError(msg)
        check_timeout_max("heartbeat_interval", heartbeat_interval)
        super().__init__(lock_file, **kwargs)
        self._lease_duration = lease_duration
        self._heartbeat_interval = heartbeat_interval
        self._on_compromise = on_compromise
        # Concurrent threads must start with the same shared claim.
        if not self.is_thread_local():
            self._context.lease_claim = LeaseClaim()

    @property
    def lease_duration(self) -> float:
        """The staleness in seconds after which a contender may take this claim."""
        return self._lease_duration

    @property
    def token(self) -> str | None:
        """The current claim token, or ``None`` while the lease is released."""
        return self._claim.token

    @property
    def _claim(self) -> LeaseClaim:
        # Another thread's failed acquire must leave the holder's heartbeat running.
        state = self._hold_state()
        if (claim := state.lease_claim) is None:
            claim = state.lease_claim = LeaseClaim()
        return claim

    @property
    def compromise(self) -> LeaseCompromise | None:
        """
        The last claim loss, or ``None``. The value survives release until the next acquire. Release may detect a loss
        before the heartbeat does. Only the heartbeat calls ``on_compromise``. Release a lost claim before reacquiring.
        """
        return self._claim.compromise

    @override
    def _singleton_extra_mismatches(self, kwargs: Mapping[str, ExtraValue], /) -> dict[str, tuple[str, str]]:
        mismatches = super()._singleton_extra_mismatches(kwargs)
        lease_duration: Final[float] = seconds("lease_duration", kwargs.get("lease_duration", _DEFAULT_LEASE_DURATION))
        if lease_duration != self._lease_duration:
            mismatches["lease_duration"] = (str(lease_duration), str(self._lease_duration))
        heartbeat_interval: Final[float] = (
            self._lease_duration / 3
            if (passed := kwargs.get("heartbeat_interval")) is None
            else seconds("heartbeat_interval", passed)
        )
        if heartbeat_interval != self._heartbeat_interval:
            mismatches["heartbeat_interval"] = (str(passed), str(self._heartbeat_interval))
        # Equal callables can close over different state.
        if (on_compromise := kwargs.get("on_compromise")) is not self._on_compromise:
            mismatches["on_compromise"] = (str(on_compromise), str(self._on_compromise))
        return mismatches

    @override
    def _acquire(self) -> None:
        claim = self._claim
        self._stop_heartbeat()  # no earlier claim's heartbeat outlives the acquisition of the next one
        # The marker write needs the token before acquisition commits.
        claim.token = token = secrets.token_hex(16)
        claim.compromise = None
        try:
            super()._acquire()
        except BaseException:
            claim.token = None
            raise
        # The heartbeat thread cannot read the acquiring thread's local claim.
        if (fd := self._context.lock_file_fd) is not None and (
            identity := self._context.lock_file_fd_identity
        ) is not None:
            self._start_heartbeat(claim, fd, identity, token)
        else:
            claim.token = None

    def _stop_heartbeat(self) -> None:
        claim = self._claim
        if (heartbeat := claim.heartbeat) is None:
            return
        claim.heartbeat = None
        # A finalizer can run on this heartbeat thread while it holds the event's lock.
        if heartbeat.thread is current_thread():
            return
        heartbeat.stop.set()
        # A frozen daemon cannot finish a join during interpreter shutdown.
        if heartbeat.thread.ident is not None and not sys.is_finalizing():
            heartbeat.thread.join(timeout=self._heartbeat_interval)

    def _start_heartbeat(self, claim: LeaseClaim, fd: int, identity: tuple[int, int], token: str) -> None:
        # An old heartbeat must never adopt a new hold's stop event.
        stop: Final[Event] = Event()
        loop: Final[_RefreshLoop] = _RefreshLoop(
            # A strong reference from the worker would prevent the dropped lease from being finalized.
            report=WeakMethod(self._report_compromise, lambda _: setattr(claim, "token", None)),
            lock_file=self._lock_path,
            claim=claim,
            fd=fd,
            identity=identity,
            token=token,
            stop=stop,
            interval=self._heartbeat_interval,
            duration=self._lease_duration,
        )
        thread: Final[Thread] = Thread(target=loop.run, name=f"filelock-lease-{os.getpid()}", daemon=True)
        # Release may race acquisition before the worker starts.
        claim.heartbeat = LeaseHeartbeat(thread=thread, stop=stop)
        thread.start()

    def _report_compromise(
        self,
        claim: LeaseClaim,
        reason: CompromiseReason,
        error: OSError | None,
        token: str,
    ) -> None:
        # The heartbeat must report to the acquiring thread's claim, even if release has since cleared its token.
        claim.compromise = LeaseCompromise(lock_file=self.lock_file, token=token, reason=reason, error=error)
        if self._on_compromise is not None:
            self._on_compromise(claim.compromise)

    @override
    def _raise_if_hold_unusable(self) -> None:
        super()._raise_if_hold_unusable()
        claim: Final[LeaseClaim] = self._claim
        if (compromise := claim.compromise) is not None and compromise.token == claim.token:
            msg = (
                f"Cannot acquire {self.lock_file}: the current claim was lost ({compromise.reason}), "
                "release it before acquiring again"
            )
            raise RuntimeError(msg)

    @override
    def _release(self) -> None:
        self._stop_heartbeat()
        if sys.platform != "win32":  # pragma: win32 no cover
            self._record_unreported_loss()
        self._claim.token = None
        super()._release()

    def _record_unreported_loss(self) -> None:  # pragma: win32 no cover
        if (
            (token := self._claim.token) is None
            or self._claim.compromise is not None
            or (identity := self._context.lock_file_fd_identity) is None
        ):
            return
        fd = self._context.lock_file_fd
        assert fd is not None  # ruff:ignore[assert]  # _release runs only while the descriptor is held
        with suppress(OSError):
            try:
                marker = os.lstat(self._lock_path)
            except FileNotFoundError:
                reason: CompromiseReason = "marker-missing"
            else:
                if (marker.st_dev, marker.st_ino) == identity:
                    return
                reason = "owner-changed"
            held = os.fstat(fd)
            if held.st_nlink:
                if reason == "marker-missing" and _parent_is_missing(self._lock_path):
                    return
                if reason == "owner-changed" and self._marker_has_break_name(held):
                    return
                # An exchange or directory rename can roll back while fstat runs.
                with suppress(FileNotFoundError):
                    if os.path.samestat(os.lstat(self._lock_path), held):
                        return
            self._claim.compromise = LeaseCompromise(lock_file=self.lock_file, token=token, reason=reason)

    def _marker_has_break_name(self, held: os.stat_result) -> bool:  # pragma: win32 no cover
        # A contender keeps the original inode under its break name until it commits or rolls back.
        prefix = f"{pathlib.Path(self._lock_path).name}.break."
        with os.scandir(pathlib.Path(self._lock_path).parent) as names:
            for name in names:
                if name.name.startswith(prefix):
                    with suppress(FileNotFoundError):
                        if os.path.samestat(name.stat(follow_symlinks=False), held):
                            return True
        return False

    @override
    def _reset_after_fork_in_child(self) -> None:  # pragma: forked child
        super()._reset_after_fork_in_child()
        # Fork discards the parent's claim. Child threads must share its replacement.
        if not self.is_thread_local():
            self._context.lease_claim = LeaseClaim()

    @override
    def _published_record(self) -> OwnerRecord:
        return super()._published_record()._replace(token=self._claim.token, lease_duration=self._lease_duration)

    @override
    def _try_break_stale_lock(self) -> None:
        # Windows can refuse renames of open files, and another contender may have recovered the marker.
        with suppress(OSError), pin_inode(self._lock_path) as pinned:
            self._try_break_pinned_lock(pinned)

    def _try_break_pinned_lock(self, pinned: int | None) -> None:
        if (peer := self._read_peer()) is None:
            # Legacy, strict and partly written markers follow the exclusive lock's recovery rules.
            super()._try_break_stale_lock()
            return
        owner, marker = peer
        if pinned not in {None, marker.st_ino}:  # pragma: win32 no cover  # Windows pins nothing
            return  # replaced before the read, so nothing keeps the number read from reuse
        if owner.mode != "unknown" and owner_is_stale(owner.pid, owner.hostname, owner.start):
            self._take_over(marker, owner.pid)
            return
        # Only a lease holder agrees to be superseded by age.
        if owner.mode == "lease" and owner.lease_duration != self._lease_duration:
            msg = (
                f"{self.lock_file} holds a lease of {owner.lease_duration!r}s but this contender configured "
                f"{self._lease_duration!r}s; every contender for a path must agree on lease_duration"
            )
            raise LeaseSettingsMismatch(msg)
        if owner.mode == "lease" and self._marker_unchanged_for(marker) >= self._lease_duration:
            self._take_over(marker, None)

    def _read_peer(self) -> tuple[OwnerRecord, os.stat_result] | None:
        with suppress(OSError, ValueError):
            content, marker = read_lock_file(self._lock_path)
            if (owner := parse_marker(content)) is not None:
                return owner, marker
        return None


class LeaseClaim:
    """
    State of a soft lease in one lock context.

    :ivar token: identity written to the marker for the current claim, or None
    :ivar compromise: why the claim was lost, or None
    :ivar heartbeat: active refresh thread and stop event, or None
    """

    __slots__ = ("compromise", "heartbeat", "token")

    token: str | None
    compromise: LeaseCompromise | None
    heartbeat: LeaseHeartbeat | None

    def __init__(self) -> None:
        self.token = None
        self.compromise = None
        self.heartbeat = None


@dataclass(frozen=True, slots=True, kw_only=True)
class _RefreshLoop:
    report: WeakMethod[Callable[[LeaseClaim, CompromiseReason, OSError | None, str], None]]
    lock_file: str
    claim: LeaseClaim
    fd: int
    identity: tuple[int, int]
    token: str
    stop: Event
    interval: float
    duration: float

    def run(self) -> None:
        # Transient filesystem errors matter once the claim could expire before the next refresh.
        last_success, missing = time.monotonic(), False
        while not self.stop.wait(self.interval) and self.claim.token == self.token:
            outcome, error = self._refresh()
            if outcome == "ok":
                last_success, missing = time.monotonic(), False
                continue
            # A competing break may briefly exchange the marker aside before restoring it.
            if outcome in {"marker-missing", "owner-changed"} and not missing:
                missing = True
                continue
            if outcome == "transient" and time.monotonic() - last_success < self.duration - self.interval:
                continue
            if (report := self.report()) is not None:
                report(self.claim, "refresh-failed" if outcome == "transient" else outcome, error, self.token)
            return

    def _refresh(self) -> tuple[_RefreshOutcome, OSError | None]:
        try:
            st = os.lstat(self.lock_file)
        except FileNotFoundError as error:
            return self._refresh_unnamed(error)
        except OSError as error:
            return "transient", error
        if (st.st_dev, st.st_ino) != self.identity:
            return "owner-changed", None
        return self._touch()

    def _refresh_unnamed(self, name_error: FileNotFoundError) -> tuple[_RefreshOutcome, OSError | None]:
        # A moved parent can keep this marker live. A hard link elsewhere cannot.
        try:
            linked = os.fstat(self.fd).st_nlink > 0
        except OSError as error:
            return "transient", error
        if not linked:
            return "marker-missing", name_error
        try:
            if _parent_is_missing(self.lock_file):
                return self._touch()
        except OSError as error:
            return "transient", error
        return "marker-missing", name_error

    def _touch(self) -> tuple[_RefreshOutcome, OSError | None]:
        try:
            touch(self.lock_file, fd=self.fd)
        except OSError as error:
            return "transient", error
        return "ok", None


@dataclass(frozen=True)
class LeaseCompromise:
    """
    Why a held lease stopped being this process's to hold, and the error that ended its refresh, if any.

    :param lock_file: the path of the lock the lease was held on
    :param token: the token of the claim that was lost
    :param reason: what took the claim away: the marker vanished, its owner changed, a refresh failed, or it was evicted
    :param error: the error that ended the refresh, when a refresh failed with one
    """

    lock_file: str
    token: str
    reason: CompromiseReason
    error: Exception | None = None


def _parent_is_missing(path: str) -> bool:
    try:
        os.lstat(pathlib.Path(path).parent)
    except FileNotFoundError:
        return True
    return False


@dataclass(frozen=True, slots=True, kw_only=True)
class LeaseHeartbeat:
    """
    Refresh thread for one lease claim.

    :param thread: thread that refreshes the marker
    :param stop: event that asks the thread to stop refreshing
    """

    thread: Thread
    stop: Event


# Existing pickles name the heartbeat class here.
_Heartbeat = LeaseHeartbeat


__all__ = [
    "CompromiseReason",
    "LeaseClaim",
    "LeaseCompromise",
    "LeaseHeartbeat",
    "SoftFileLease",
]
