"""Owner inspection and stale-owner checks for marker locks."""

from __future__ import annotations

__lazy_modules__ = ["contextlib", "filelock._filesystem", "filelock._identity", "filelock._soft"]

import os
from contextlib import suppress

from filelock._core import override
from filelock._filesystem import pin_inode, write_all
from filelock._identity import host_name, owner_is_current_process, owner_is_stale, process_start_token
from filelock._soft import OwnerMode, OwnerRecord, encode_marker, parse_marker, read_lock_file

from ._lock import SoftFileLock


class MarkerSoftFileLock(SoftFileLock):
    """An existence lock whose marker carries a protocol 2 owner record."""

    #: Age-based expiry requires a lease contract; an exclusive holder grants none.
    _owner_mode: OwnerMode = "exclusive"

    @property
    def owner(self) -> OwnerRecord | None:
        """The protocol 2 owner record, or ``None`` for a missing, malformed or legacy marker."""
        return self._read_owner()

    def _read_owner(self) -> OwnerRecord | None:
        with suppress(OSError, ValueError):
            return parse_marker(read_lock_file(self._lock_path)[0])
        return None

    @property
    @override
    def pid(self) -> int | None:
        """The PID in the owner record, or ``None`` if the marker is missing or unreadable."""
        return None if (owner := self._read_owner()) is None else owner.pid

    @property
    @override
    def is_lock_held_by_us(self) -> bool:
        """Whether the owner record identifies this process."""
        owner = self._read_owner()
        return owner is not None and owner_is_current_process(owner.pid, owner.hostname, owner.start)

    def force_break(self) -> None:
        """Remove the marker. A live holder can continue working after a forced break."""
        self.break_lock()

    @override
    def _try_break_stale_lock(self) -> None:
        with suppress(OSError, ValueError), pin_inode(self._lock_path) as pinned:
            content, marker = read_lock_file(self._lock_path)
            owner: OwnerRecord | None
            if pinned not in {None, marker.st_ino}:  # pragma: win32 no cover  # Windows pins nothing
                return  # replaced before the read, so nothing keeps the number read from reuse
            if (owner := parse_marker(content)) is None:
                super()._try_break_stale_lock()
            elif owner.mode != "unknown" and owner_is_stale(owner.pid, owner.hostname, owner.start):
                self._take_over(marker, owner.pid)

    @classmethod
    @override
    def _recorded_holder(cls, content: str | None) -> tuple[int, str] | None:
        if (owner := parse_marker(content)) is not None:
            return owner.pid, owner.hostname
        return super()._recorded_holder(content)

    @classmethod
    @override
    def _marker_is_live(cls, content: str | None, breaker_pid: int) -> bool:  # pragma: win32 no cover
        if (owner := parse_marker(content)) is None:
            return super()._marker_is_live(content, breaker_pid)
        return owner.mode == "unknown" or (
            (owner.pid != breaker_pid or owner.hostname != host_name())
            and not owner_is_stale(owner.pid, owner.hostname, owner.start)
        )

    @override
    def _write_lock_info(self, fd: int) -> None:
        write_all(fd, encode_marker(self._published_record()))

    def _published_record(self) -> OwnerRecord:
        return OwnerRecord(
            pid=os.getpid(),
            hostname=host_name(),
            mode=self._owner_mode,
            start=process_start_token(os.getpid()),
        )


__all__ = [
    "MarkerSoftFileLock",
]
