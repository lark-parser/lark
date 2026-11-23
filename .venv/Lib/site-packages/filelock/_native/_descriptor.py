"""A minimal native lock over a caller-owned file descriptor, contending with :class:`FileLock` on the same file."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from importlib.machinery import ModuleSpec

__spec__ = cast("ModuleSpec", __spec__)

__lazy_modules__ = ["filelock._core", "threading", f"{__spec__.parent}._unix", f"{__spec__.parent}._windows"]

import sys
import time
from threading import TIMEOUT_MAX
from typing import Final

from filelock._core import check_blocking, seconds

if sys.platform == "win32":  # pragma: win32 cover
    from ._windows import (
        lock_fd_nonblocking,
        unlock_fd,
    )
else:  # pragma: win32 no cover
    from ._unix import (
        lock_fd_nonblocking,
        unlock_fd,
    )


def lock_descriptor(fd: int, *, blocking: bool = True, poll_interval: float = 0.05) -> bool:
    """
    Lock a caller-owned descriptor with the same primitive as :class:`FileLock`.

    Unix locks the whole file with :func:`fcntl.flock`. Windows locks one byte at offset zero with
    ``LockFileEx`` and requires a synchronous handle. The caller retains the descriptor and its file position.

    :param fd: open descriptor to lock
    :param blocking: wait for the lock, or return ``False`` on contention
    :param poll_interval: seconds between blocking attempts, in ``(0, threading.TIMEOUT_MAX]``
    :returns: whether the lock was acquired
    :raises OSError: the native operation failed or is unavailable
    :raises TypeError: *blocking* is not a bool or the blocking poll interval is not a number
    :raises ValueError: the blocking poll interval is out of range

    .. versionadded:: 3.30.0
    """
    check_blocking(blocking)
    if not blocking:
        return lock_fd_nonblocking(fd)
    # time.sleep raises OverflowError past TIMEOUT_MAX; nan fails both comparisons.
    if not 0 < (poll_interval := seconds("poll_interval", poll_interval)) <= TIMEOUT_MAX:
        msg: Final[str] = f"poll_interval must be greater than 0 and at most {TIMEOUT_MAX}, got {poll_interval}"
        raise ValueError(msg)
    while not lock_fd_nonblocking(fd):
        time.sleep(poll_interval)
    return True


def unlock_descriptor(fd: int) -> None:
    """
    Release a lock taken by :func:`lock_descriptor` and leave the descriptor open.

    :param fd: descriptor holding the lock
    :raises OSError: the native unlock failed or is unavailable

    .. versionadded:: 3.30.0
    """
    unlock_fd(fd)


__all__ = [
    "lock_descriptor",
    "unlock_descriptor",
]
