"""Recovery of stale or displaced lock markers."""

from __future__ import annotations

__lazy_modules__ = [
    "contextlib",
    "filelock._filesystem",
    "filelock._identity",
    "filelock._soft",
    "pathlib",
    "secrets",
    "typing",
]

import os
import re
import secrets
import threading
import time
from contextlib import suppress
from pathlib import Path
from typing import Final

from filelock._core import override
from filelock._filesystem import (
    break_lock_file,
    break_marker_path,
    break_marker_pid,
    exchange_back,
    exchange_names,
    exchange_supported,
    foreign_owner,
    pin_inode,
)
from filelock._identity import host_name, owner_is_stale
from filelock._soft import (
    MALFORMED_LOCK_AGE_THRESHOLD,
    STRICT_SOFT_SENTINEL_RECORD,
    parse_lock_holder,
    read_lock_file,
)

from ._publication import MarkerPublication, file_identity

RECORDLESS_MARKER: Final[str] = ""
_CLAIMS_IN_PROGRESS: Final[set[str]] = set()
_CLAIMS_LOCK: Final[threading.Lock] = threading.Lock()
_RECOVERY_NAME: Final[re.Pattern[str]] = re.compile(
    r"""
    (?P<operation>break|restore) \.
    (?P<pid>[0-9]+) \.  # writers use ASCII decimal PIDs
    [0-9a-f]{32}         # token_hex(16)
    """,
    re.VERBOSE,
)


class MarkerRecovery(MarkerPublication):
    _marker_seen: tuple[tuple[float, int, int], float] | None = None

    @override
    def _try_break_stale_lock(self) -> None:
        with suppress(OSError, ValueError), pin_inode(self._lock_path) as pinned:
            content, marker = read_lock_file(self._lock_path)
            if pinned not in {None, marker.st_ino}:  # pragma: win32 no cover  # Windows pins nothing
                return  # the replacement inode can be reused before takeover
            if content == STRICT_SOFT_SENTINEL_RECORD:  # pragma: needs hard-link
                return
            # Older holders leave empty markers throughout their hold.
            if content == RECORDLESS_MARKER:
                return
            holder = parse_lock_holder(content)

            if holder is None:
                # A peer may still be writing the marker after exclusive creation.
                if self._marker_unchanged_for(marker) >= MALFORMED_LOCK_AGE_THRESHOLD:
                    self._take_over(marker, break_marker_pid(content))
                return

            if owner_is_stale(*holder):
                self._take_over(marker, holder[0])

    def _marker_unchanged_for(self, marker: os.stat_result) -> float:
        # A peer can recreate a marker with the same inode and mtime.
        now: Final[float] = time.monotonic()
        key: Final[tuple[float, int, int]] = marker.st_mtime, marker.st_ino, marker.st_ctime_ns
        if (seen := self._marker_seen) is None or seen[0] != key:
            self._marker_seen = key, now
            return 0.0
        return now - seen[1]

    def _take_over(self, marker: os.stat_result, breaker_pid: int | None) -> None:
        # Atomic exchange keeps a marker at the lock path throughout takeover.
        if exchange_supported():  # pragma: win32 no cover
            self._take_over_by_exchange(marker, breaker_pid)
        else:
            break_lock_file(self._lock_path, marker.st_mtime, marker.st_ino)

    def _take_over_by_exchange(self, marker: os.stat_result, breaker_pid: int | None) -> None:  # pragma: win32 no cover
        if (current := os.lstat(self._lock_path)).st_mtime != marker.st_mtime or current.st_ino != marker.st_ino:
            return
        if breaker_pid is not None and self._restore_stranded_marker(breaker_pid, marker):
            return
        aside: Final[str] = break_marker_path(self._lock_path, os.getpid())
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        opened: Final[list[int]] = []
        identity: tuple[int, int] | None = None
        exchanged = False
        try:
            fd: Final[int] = self._create_marker(aside, flags, opened)
            identity = file_identity(os.fstat(fd))
            self._apply_explicit_mode(fd)
            self._write_lock_info(fd)
            # A peer may have taken the marker while we published ours.
            if (current := os.lstat(self._lock_path)).st_mtime != marker.st_mtime or current.st_ino != marker.st_ino:
                return
            # A signal can raise after exchange commits but before Python receives its result.
            exchanged = True
            if not exchange_names(aside, self._lock_path):
                exchanged = False
                return  # a rename would leave the lock path empty
            if (taken := os.lstat(aside)).st_mtime != marker.st_mtime or taken.st_ino != marker.st_ino:
                return  # a peer recreated the marker, which the cleanup below swaps back
            Path(aside).unlink()
            exchanged = False
            self._mark_descriptor_owned(fd, identity)
        finally:
            if opened and (identity is None or self._context.pending_lock_file_fd is not None):
                self._abandon_take_over(opened[0], aside, put_back=exchanged)

    def _restore_stranded_marker(self, breaker_pid: int, marker: os.stat_result) -> bool:  # pragma: win32 no cover
        # Renaming a stranded record claims its recovery, so concurrent recoverers cannot reverse each other's exchange.
        if (candidates := self._stranded_candidates(breaker_pid)) is None:
            return True
        return any(self._recover_claimed(path, breaker_pid, marker, adopt=abandoned) for path, abandoned in candidates)

    def _stranded_candidates(self, breaker_pid: int) -> list[tuple[str, bool]] | None:  # pragma: win32 no cover
        directory, name = os.path.split(self._lock_path)
        prefix = f"{name}."
        candidates: list[tuple[str, bool]] = []
        with os.scandir(directory or os.curdir) as entries:
            for entry in entries:
                if not entry.name.startswith(prefix) or not entry.is_file(follow_symlinks=False):
                    continue
                if (found := _RECOVERY_NAME.fullmatch(entry.name, len(prefix))) is None:
                    continue
                path = str(Path(directory) / entry.name)
                if found["operation"] == "break" and found["pid"] == str(breaker_pid):
                    # The PID may now belong to another live breaker.
                    if 1 <= breaker_pid <= 2**31 - 1 and not owner_is_stale(breaker_pid, host_name(), None):
                        return None
                    candidates.append((path, False))
                elif found["operation"] == "restore" and 1 <= (recoverer := int(found["pid"])) <= 2**31 - 1:
                    # Reject out-of-range PIDs before passing them to the OS.
                    ours = recoverer == os.getpid()
                    if not (ours or owner_is_stale(recoverer, host_name(), None)):
                        return None
                    candidates.append((path, ours))
        return sorted(candidates)

    def _recover_claimed(
        self, path: str, breaker_pid: int, marker: os.stat_result, *, adopt: bool
    ) -> bool:  # pragma: win32 no cover
        # Registration must precede the rename so another local thread cannot adopt a live recovery.
        own: Final[str] = path if adopt else f"{self._lock_path}.restore.{os.getpid()}.{secrets.token_hex(16)}"
        if not _begin_claim(own):
            return True
        try:
            if not adopt:
                try:
                    Path(path).rename(own)
                except OSError:  # a peer that won the rename now holds the record, so the lock counts as held
                    return True
            return self._restore_claimed(own, breaker_pid, marker)
        finally:
            _end_claim(own)

    def _restore_claimed(self, own: str, breaker_pid: int, marker: os.stat_result) -> bool:  # pragma: win32 no cover
        try:
            content, record = read_lock_file(own)
        except OSError:
            self._return_claim(own, breaker_pid)
            return True
        if not self._marker_is_live(content, breaker_pid):
            with suppress(OSError):
                Path(own).unlink()
            return False
        with suppress(OSError):
            current = os.lstat(self._lock_path)
            if (
                foreign_owner(record, Path(self._lock_path).parent.stat()) is None
                and (current.st_ino, current.st_mtime) == (marker.st_ino, marker.st_mtime)
                and exchange_names(own, self._lock_path)
            ):
                if os.lstat(own).st_ino == marker.st_ino:
                    Path(own).unlink()
                    return True
                # A replacement raced our check. Exchange back before returning the claim.
                exchange_names(own, self._lock_path)
        self._return_claim(own, breaker_pid)
        return True

    def _return_claim(self, own: str, breaker_pid: int) -> None:  # pragma: win32 no cover
        # A later poll can retry a refused rename under this process's PID.
        with suppress(OSError):
            Path(own).rename(break_marker_path(self._lock_path, breaker_pid))

    @classmethod
    def _marker_is_live(cls, content: str | None, breaker_pid: int) -> bool:  # pragma: win32 no cover
        if content == STRICT_SOFT_SENTINEL_RECORD:  # pragma: needs hard-link
            return True
        if content == RECORDLESS_MARKER:
            # A pre-3.22 holder keeps its marker empty until release.
            return True
        # Another host can have a live holder with the same PID as our breaker.
        return (
            (holder := parse_lock_holder(content)) is not None
            and (holder[0] != breaker_pid or holder[1] != host_name())
            and not owner_is_stale(*holder)
        )

    def _abandon_take_over(self, fd: int, aside: str, *, put_back: bool) -> None:  # pragma: win32 no cover
        self._mark_descriptor_released()
        put_back_done = not put_back
        try:
            if put_back:
                put_back_done = exchange_back(self._lock_path, aside, fd, unlink_settled_aside=False)
                if put_back_done:
                    with suppress(OSError):
                        Path(aside).unlink(missing_ok=True)
        finally:
            try:
                # Our open descriptor pins the inode while checking both names.
                own: Final[os.stat_result] = os.fstat(fd)
                for name in (self._lock_path, aside):
                    if name == self._lock_path and not put_back_done:
                        continue
                    with suppress(FileNotFoundError):
                        if os.path.samestat(os.lstat(name), own):
                            Path(name).unlink()
            finally:
                os.close(fd)

    @override
    def _try_break_expired_lock(self) -> None:
        if (lifetime := self._context.lifetime) is None:
            return
        with suppress(OSError), pin_inode(self._lock_path) as pinned:
            content, marker = read_lock_file(self._lock_path)
            if pinned not in {None, marker.st_ino} or time.time() - marker.st_mtime < lifetime:
                return
            holder = self._recorded_holder(content)
            self._take_over(marker, None if holder is None else holder[0])

    @classmethod
    def _recorded_holder(cls, content: str | None) -> tuple[int, str] | None:
        return None if (holder := parse_lock_holder(content)) is None else holder[:2]


def _begin_claim(name: str | Path) -> bool:  # pragma: win32 no cover
    # The token identifies the claim even when the directory has another spelling.
    with _CLAIMS_LOCK:
        if (key := Path(name).name) in _CLAIMS_IN_PROGRESS:
            return False
        _CLAIMS_IN_PROGRESS.add(key)
        return True


def _end_claim(name: str | Path) -> None:  # pragma: win32 no cover
    with _CLAIMS_LOCK:
        _CLAIMS_IN_PROGRESS.discard(Path(name).name)


__all__ = [
    "RECORDLESS_MARKER",
    "MarkerRecovery",
]
