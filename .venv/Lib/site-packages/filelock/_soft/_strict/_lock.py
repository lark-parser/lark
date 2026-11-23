"""Exclusive soft locking through ordered filesystem claims."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from importlib.machinery import ModuleSpec

__spec__ = cast("ModuleSpec", __spec__)

__lazy_modules__ = [
    "concurrent.futures",
    "contextlib",
    "filelock._filesystem",
    "pathlib",
    "secrets",
    "threading",
    f"{__spec__.parent}._claims",
    f"{__spec__.parent}._directories",
    f"{__spec__.parent}._publication",
    f"{__spec__.parent}._scan",
    f"{__spec__.parent}._sentinel",
    f"{__spec__.parent}._windows",
]

import contextlib
import os
import secrets
import sys
import time
from concurrent.futures import Future
from errno import EEXIST, ENOENT
from pathlib import Path
from threading import Thread
from typing import Final, cast

from filelock._core import SoftFileLockProtocolError, ThreadLocalFileContext, override, raise_cleanup_errors
from filelock._filesystem import foreign_owner

from ._claims import (
    CLAIM_DIRECTORY_NAME,
    TOKEN_HEX_LENGTH,
    ClaimEntryLimitError,
    PrivateRecordReclaimedError,
    RetryDoorwayError,
    StrictSoftFileClaim,
    claim_name,
    claim_record,
    private_record_name,
)
from ._directories import (
    LIMITS,
    SUPPORTS,
    ensure_claim_directory,
    ensure_protocol_directory,
    file_identity,
    open_claim_directory,
    pin_claim_directory,
    scandir_relative,
)
from ._publication import (
    link_no_replace,
    publish_record,
    raise_if_hard_links_unsupported,
    raise_recorded_errors,
    unlink_in_directory,
    unlink_owner_path_result,
)
from ._release import TimedReleaseLock
from ._scan import read_existing_claims
from ._sentinel import inspect_lock_path, open_or_create_sentinel

if sys.platform == "win32":  # pragma: win32 cover
    from filelock._filesystem import oplock_wait_cancelled

    from ._windows import publish_deletable_claim

if TYPE_CHECKING:
    from filelock._core import FileLockContext

_COORDINATION_SUFFIX: Final[str] = ".filelock"


class StrictSoftFileLock(TimedReleaseLock):
    """Portable fail-closed lock based on immutable owner claims."""

    _preserve_lock_file_supported: bool = True
    _on_acquired_supported: bool = False
    # A strict claim can only be cleared by its owner or force_break().
    _lifetime_supported: bool = False
    _lifetime_unsupported_reason: str = "a strict claim is never broken by age, only by force_break()"
    # Jitter reduces simultaneous directory scans under contention.
    _poll_backoff_cap: float = 0.05
    _occupant_seen: tuple[tuple[float, int, int], float] | None = None

    @property
    def claims(self) -> tuple[StrictSoftFileClaim, ...]:
        """Published claims that block acquisition."""
        # Inspection skips age-based cleanup so it can run without writing a clock probe.
        return read_existing_claims(self.lock_file, self._claim_directory, entry_limit=None, verify_server=False)

    @property
    def _claim_directory(self) -> Path:
        if self._context.owner_claim_paths:
            return Path(self._context.owner_claim_paths[0]).parent
        return Path(f"{self._resolve_lock_path()}{_COORDINATION_SUFFIX}") / CLAIM_DIRECTORY_NAME

    @property
    def lock_path_occupant(self) -> str | None:
        """
        Describe an occupant blocking the strict sentinel, or return ``None`` for an empty path or the sentinel.

        A soft-lock marker can block acquisition without appearing in :attr:`claims`. The description includes
        its PID and host when available. When acquire raises :class:`~filelock.SoftFileLockProtocolError`,
        inspect the occupant before removing it.
        """
        try:
            fd, _, occupant = inspect_lock_path(Path(self._resolve_lock_path()))
        except FileNotFoundError:
            return None
        if fd is None:
            return occupant
        os.close(fd)
        return None

    @override
    def _acquire(self) -> None:
        # A leftover claim from a failed withdrawal would block this instance on its next attempt.
        deadline = self._context.claim_deadline
        lock_path = Path(self._lock_path)
        coordination_directory = Path(f"{lock_path}{_COORDINATION_SUFFIX}")
        claim_directory = coordination_directory / CLAIM_DIRECTORY_NAME
        # Search permission lets readers inspect claims without granting them directory writes.
        directory_mode: Final[int] = (mode := self._open_mode()) | (mode & 0o444) >> 2
        try:
            self._discard_pending_doorways(exited_only=True, deadline=deadline)
            ensure_protocol_directory(self.lock_file, coordination_directory, directory_mode)
            ensure_claim_directory(self.lock_file, claim_directory, directory_mode)
            sentinel_fd = open_or_create_sentinel(
                self.lock_file, lock_path, self._open_mode(), self._occupant_unchanged_for
            )
        except RetryDoorwayError:
            return
        if sentinel_fd is None:
            return
        try:
            sentinel_identity = self._sentinel_identity(sentinel_fd, lock_path)
        except BaseException as inspection_error:  # preserve inspection and descriptor cleanup errors
            try:
                os.close(sentinel_fd)
            except BaseException as close_error:  # ruff:ignore[blind-except]  # preserve inspection and descriptor cleanup errors
                raise_cleanup_errors("strict sentinel inspection cleanup failed", inspection_error, close_error)
            raise
        self._mark_descriptor_pending(sentinel_fd, sentinel_identity)
        try:
            if won := self._attempt_doorway(claim_directory):
                self._mark_descriptor_owned(sentinel_fd, sentinel_identity)
        except RetryDoorwayError:
            won = False
        except BaseException as acquisition_error:
            # Once recorded as held, the acquire's rollback releases the claim instead.
            if not self.is_locked:
                self._discard_doorway(deadline, acquisition_error)
            raise
        if not won:
            self._discard_doorway(deadline)

    def _discard_pending_doorways(self, *, exited_only: bool, deadline: float | None) -> None:
        if (self._context.claim_withdrawal is not None or self._context.owner_claim_paths) and not self.is_locked:
            self._discard_doorway(deadline)
        if not isinstance(context := self._context, ThreadLocalFileContext):
            return
        # Only this registry reaches an exited thread's thread-local doorway; a live thread finishes its own.
        own = context.current
        with self._transition_lock:
            for pending, thread in self._thread_pending.copy().values():
                if exited_only and thread.is_alive():
                    continue
                context.current = pending
                try:
                    self._discard_doorway(deadline)
                finally:
                    context.current = own

    def _occupant_unchanged_for(self, occupant: os.stat_result) -> float:
        # A monotonic interval avoids comparing wall clocks across hosts.
        key, now = (occupant.st_mtime, occupant.st_ino, occupant.st_size), time.monotonic()
        if (seen := self._occupant_seen) is None or seen[0] != key:
            self._occupant_seen = key, now
            return 0.0
        return now - seen[1]

    def _sentinel_identity(self, fd: int, path: Path) -> tuple[int, int]:
        found = os.fstat(fd)
        if (
            sys.platform != "win32" and (owner := foreign_owner(found, path.parent.stat(), fd=fd)) is not None
        ):  # pragma: needs foreign-sticky-tmp
            reason = f"sentinel belongs to uid {owner}, not to this process's account or the directory's owner"
            raise SoftFileLockProtocolError(self.lock_file, None, reason)
        return file_identity(found)

    def _attempt_doorway(self, claim_directory: Path) -> bool:
        try:
            # Leave room for both public claims, the private record and a filesystem clock probe.
            if read_existing_claims(self.lock_file, claim_directory, entry_limit=LIMITS.entries - 4):
                return False
        except ClaimEntryLimitError as error:
            raise SoftFileLockProtocolError(self.lock_file, None, str(error)) from None

        return self._publish_claims(claim_directory)

    def _publish_claims(self, claim_directory: Path) -> bool:
        token = secrets.token_hex(TOKEN_HEX_LENGTH // 2)
        intent_name = claim_name("intent", token)
        intent_path = str(claim_directory / intent_name)
        # An interrupt after publication must leave the name available for withdrawal.
        self._context.owner_claim_paths = (intent_path,)
        try:
            publication_cleanup_error = self._publish_intent_claim(claim_directory, intent_name, intent_path, token)
        except PrivateRecordReclaimedError:  # pragma: win32 no cover
            return False
        except (NotImplementedError, OSError) as error:
            if sys.platform == "win32" and isinstance(error, BlockingIOError):  # pragma: win32 cover
                return False
            raise_if_hard_links_unsupported(self.lock_file, error)
            if isinstance(error, OSError) and error.errno == EEXIST:
                # Another file holds the name, so it is not this owner's to remove.
                self._context.owner_claim_paths = ()
                _, cleanup_errors = self._unlink_owner_claims(self._hold_state(), deadline=self._context.claim_deadline)
                if cleanup_errors:  # pragma: win32 cover
                    raise_recorded_errors("strict claim protection cleanup failed", cleanup_errors)
                return False
            raise
        if publication_cleanup_error is not None:  # pragma: needs dir-fd
            raise publication_cleanup_error

        claims = read_existing_claims(self.lock_file, claim_directory, entry_limit=LIMITS.entries)
        if (
            not claims
            or any(claim.state == "held" for claim in claims)
            or min(claim.name for claim in claims) != intent_name
        ):
            return False

        held_name = claim_name("held", token)
        self._context.owner_claim_paths = (str(claim_directory / held_name), intent_path)
        publication_cleanup_error = self._publish_held_claim(claim_directory, intent_name, held_name, token)
        if publication_cleanup_error is not None:  # pragma: needs dir-fd
            raise publication_cleanup_error

        claims = read_existing_claims(self.lock_file, claim_directory, entry_limit=LIMITS.entries)
        # A scan may miss a newly published held claim. Its unchanged intent stays visible throughout the hold.
        return {intent_name, held_name}.issubset(claim.name for claim in claims) and min(
            claim.token for claim in claims
        ) == token

    def _publish_intent_claim(
        self, claim_directory: Path, intent_name: str, intent_path: str, token: str
    ) -> BaseException | None:
        if sys.platform == "win32":  # pragma: win32 cover
            self._context.claim_protection = pin_claim_directory(claim_directory, acquiring=True)
            self._context.claim_descriptors = {}
            self._publish_windows_claim(claim_directory, intent_name, token)
            return None
        with pin_claim_directory(claim_directory):  # pragma: win32 no cover
            return publish_record(intent_path, claim_record(token), self._open_mode(), open_claim_directory)

    def _publish_windows_claim(self, claim_directory: Path, name: str, token: str) -> None:  # pragma: win32 cover
        protection = self._context.claim_protection
        descriptors = self._context.claim_descriptors
        assert protection is not None  # ruff:ignore[assert]  # the intent opens the directory before publishing
        assert descriptors is not None  # ruff:ignore[assert]  # the intent initializes the descriptor registry
        path = str(claim_directory / name)

        def close_claim() -> None:
            if (fd := descriptors.pop(path, None)) is not None:
                os.close(fd)

        protection.callback(close_claim)
        publish_deletable_claim(
            lambda: str(claim_directory / private_record_name(name)),
            path,
            claim_record(token),
            descriptors,
            self._context.claim_deadline,
        )

    def _unlink_owner_claims(
        self, state: FileLockContext, *, deadline: float | None = None
    ) -> tuple[list[str], list[BaseException]]:
        results = [(path, unlink_owner_path_result(path, state, deadline=deadline)) for path in state.owner_claim_paths]
        remaining = [path for path, (removed, _) in results if not removed]
        errors = [error for _, (_, error) in results if error is not None]
        state.owner_claim_paths = tuple(remaining)
        if (not remaining or self._finalizing) and (  # pragma: win32 cover
            protection := state.claim_protection
        ) is not None:
            state.claim_protection = None
            state.claim_descriptors = None
            try:
                protection.close()
            except BaseException as close_error:  # ruff:ignore[blind-except]  # preserve claim cleanup failures
                errors.append(close_error)
        if self._finalizing:
            # Finalization cannot retry withdrawal or report its errors, but must still close the descriptor.
            return [], []  # pragma: needs collected-finalization
        return remaining, errors

    def _publish_held_claim(
        self, claim_directory: Path, intent_name: str, held_name: str, token: str
    ) -> BaseException | None:
        try:
            if sys.platform == "win32":  # pragma: win32 cover
                self._publish_windows_claim(claim_directory, held_name, token)
                return None
            return link_no_replace(claim_directory, intent_name, held_name)  # pragma: win32 no cover
        except (NotImplementedError, OSError) as error:
            if sys.platform == "win32" and isinstance(error, BlockingIOError):  # pragma: win32 cover
                return None
            raise_if_hard_links_unsupported(self.lock_file, error)
            if isinstance(error, OSError) and error.errno == EEXIST:
                self._context.owner_claim_paths = (str(claim_directory / intent_name),)
            raise

    def _discard_doorway(self, deadline: float | None, acquisition_error: BaseException | None = None) -> None:
        state = self._hold_state()
        if (pending := state.claim_withdrawal) is not None:  # pragma: win32 cover
            if not pending.done():
                raise RetryDoorwayError
            state.claim_withdrawal = None
            remaining, errors = pending.result()
        else:
            remaining, errors = self._unlink_owner_claims(state, deadline=deadline)
        # Withdrawal retries need only claim paths. A discarded instance cannot retry a descriptor close.
        if (fd := self._context.pending_lock_file_fd) is not None:
            self._context.pending_lock_file_fd = self._context.pending_lock_file_fd_identity = None
            try:
                self._close_released_fd(fd, default_suppresses=False)
            except BaseException as close_error:  # ruff:ignore[blind-except]  # preserve claim and sentinel cleanup errors
                errors.append(close_error)
        if (
            sys.platform == "win32" and errors and isinstance(acquisition_error, BaseExceptionGroup)
        ):  # pragma: win32 cover
            errors.insert(0, acquisition_error)
        if remaining:
            # Windows needs the original handles to withdraw after the caller times out.
            if (
                sys.platform == "win32"
                and deadline is not None
                and acquisition_error is None
                and pending is None
                and all(map(oplock_wait_cancelled, errors))
            ):  # pragma: win32 cover
                self._defer_withdrawal(state)
                return
            raise_recorded_errors("strict doorway claim cleanup failed", errors)
        self._mark_descriptor_released()
        if errors:
            raise_recorded_errors("strict doorway cleanup failed", errors)

    def _defer_withdrawal(self, state: FileLockContext) -> None:  # pragma: win32 cover
        # A caller can drop out at its deadline. Peers still need the public names withdrawn once the reader leaves.
        pending: Future[tuple[list[str], list[BaseException]]] = Future()

        def withdraw() -> None:
            if not pending.set_running_or_notify_cancel():
                return
            try:
                pending.set_result(self._unlink_owner_claims(state))
            except BaseException as error:  # ruff:ignore[blind-except]  # return the worker's failure to the owner
                pending.set_exception(error)

        worker = Thread(target=withdraw, name="filelock-claim-withdrawal", daemon=True)
        state.claim_withdrawal = pending
        try:
            worker.start()
        except BaseException:
            if pending.cancel():
                state.claim_withdrawal = None
            raise

    def force_break(self, claim_name: str) -> None:
        """
        Remove one named claim, allowing overlap if its owner still holds the protected resource.

        :param claim_name: the file name of the claim to remove, as listed by :attr:`claims`
        :raises ValueError: if *claim_name* is not one public claim basename
        :raises FileNotFoundError: if no claim with that name is in the claim directory
        """
        invalid_component = not claim_name or claim_name.startswith(".") or claim_name in {os.curdir, os.pardir}
        if invalid_component or any(separator in claim_name for separator in ("/", "\\", "\x00")):
            msg = "claim_name must be one public claim basename"
            raise ValueError(msg)
        with pin_claim_directory(directory := self._claim_directory):
            directory_fd = open_claim_directory(os.fspath(directory)) if SUPPORTS.open_dir_fd else None
            try:
                with scandir_relative((os.fspath(directory), directory_fd)) as entries:
                    if not any(entry.name == claim_name for entry in entries):
                        raise FileNotFoundError(ENOENT, os.strerror(ENOENT), claim_name)
            finally:
                if directory_fd is not None:  # pragma: needs dir-fd
                    with contextlib.suppress(OSError):
                        os.close(directory_fd)
            cleanup_error = unlink_in_directory(directory, claim_name)
        if cleanup_error is not None:  # pragma: needs dir-fd
            raise cleanup_error

    @override
    def _release_abandoned_holds(self, *, exited_only: bool) -> None:
        self._finalizing = True
        super()._release_abandoned_holds(exited_only=exited_only)
        # release() skips a doorway whose cleanup failed, as it is no hold, so a dropped instance would strand claims.
        with contextlib.suppress(Exception):
            # GraalPy defers finalizers to the host collector, so its tests cannot drive this cleanup.
            self._discard_pending_doorways(
                exited_only=exited_only, deadline=time.perf_counter()
            )  # pragma: needs collected-finalization

    @override
    def _reconcile_failed_acquire(self, canonical: str, *, levels_before: int) -> None:
        # The next acquire may resolve this relative path from a different working directory.
        self._context.claim_root = None
        super()._reconcile_failed_acquire(canonical, levels_before=levels_before)

    @override
    def _release(self) -> None:
        fd = cast("int", self._context.lock_file_fd)
        self._context.claim_root = None
        remaining, errors = self._unlink_owner_claims(self._hold_state())
        if remaining:
            raise_recorded_errors("strict claim release failed", errors)
        self._mark_descriptor_released()
        try:
            self._close_released_fd(fd, default_suppresses=False)
        except BaseException as close_error:  # ruff:ignore[blind-except]  # preserve claim and sentinel cleanup errors
            errors.append(close_error)
        if errors:
            raise_recorded_errors("strict release cleanup failed", errors)


__all__ = [
    "StrictSoftFileLock",
]
