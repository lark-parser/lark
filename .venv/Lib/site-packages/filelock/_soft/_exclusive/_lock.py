"""Exclusive file lock backed by an owner marker."""

from __future__ import annotations

__lazy_modules__ = ["contextlib", "filelock._identity", "filelock._soft", "pathlib"]

from contextlib import suppress
from pathlib import Path

from filelock._core import override
from filelock._identity import describe_host_name, host_name, owner_is_current_process
from filelock._soft import parse_lock_holder, read_lock_file

from ._recovery import RECORDLESS_MARKER, MarkerRecovery


class SoftFileLock(MarkerRecovery):
    """
    Peers can reclaim a crashed holder's PID marker on the same host. The filesystem must make exclusive creation
    and directory changes visible to every participant. Age-based expiry can admit a peer while the owner is active.
    """

    _lifetime_supported: bool = True
    _lifetime_replacements: tuple[str, str] | None = ("StrictSoftFileLock", "SoftFileLease")
    _preserve_lock_file_supported: bool = False
    _on_acquired_supported: bool = False

    @property
    def pid(self) -> int | None:
        """The PID recorded in the marker, or ``None`` if it is missing or unreadable."""
        with suppress(OSError, ValueError):
            if (holder := parse_lock_holder(read_lock_file(self._lock_path)[0])) is not None:
                return holder[0]
        return None

    @property
    def is_lock_held_by_us(self) -> bool:
        """Whether the marker identifies this process by PID, host and recorded start time."""
        with suppress(OSError, ValueError):
            if (holder := parse_lock_holder(read_lock_file(self._lock_path)[0])) is not None:
                return owner_is_current_process(*holder)
        return False

    @override
    def _unprobeable_holder(self) -> str | None:
        # This host cannot prove such a holder dead, so whoever decides whether it is gone needs its name.
        with suppress(OSError, ValueError):
            if (content := read_lock_file(self._lock_path)[0]) == RECORDLESS_MARKER:
                return "an owner that recorded no PID (a filelock release before 3.22, or one still writing its record)"
            if (holder := self._recorded_holder(content)) and holder[1] != host_name():
                return f"pid {holder[0]} on {describe_host_name(holder[1])}"
        return None

    def break_lock(self) -> None:
        """Forcibly break the lock by removing the lock file, regardless of who holds it."""
        with suppress(OSError):
            Path(self._lock_path).unlink()


__all__ = [
    "SoftFileLock",
]
