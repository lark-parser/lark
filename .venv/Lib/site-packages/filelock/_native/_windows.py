"""Windows file locking with LockFileEx."""

from __future__ import annotations

__lazy_modules__ = ["contextlib", "filelock._filesystem", "msvcrt", "typing"]

import sys
from typing import cast

from filelock._core import BaseFileLock, override

if sys.platform == "win32":  # pragma: win32 cover
    import ctypes
    import msvcrt
    import os
    from contextlib import suppress
    from ctypes import wintypes
    from typing import Final

    from filelock._filesystem import open_non_reparse_fd, raise_on_not_writable_file, unlink_without_oplock_wait

    _KERNEL32: Final[ctypes.WinDLL] = ctypes.WinDLL("kernel32", use_last_error=True)

    class _OVERLAPPED(ctypes.Structure):
        # The first two fields are pointer-sized on x64.
        _fields_ = (
            ("Internal", ctypes.c_void_p),
            ("InternalHigh", ctypes.c_void_p),
            ("Offset", wintypes.DWORD),
            ("OffsetHigh", wintypes.DWORD),
            ("hEvent", wintypes.HANDLE),
        )

    _KERNEL32.LockFileEx.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(_OVERLAPPED),
    ]
    _KERNEL32.LockFileEx.restype = wintypes.BOOL
    _KERNEL32.UnlockFileEx.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(_OVERLAPPED),
    ]
    _KERNEL32.UnlockFileEx.restype = wintypes.BOOL

    class WindowsFileLock(BaseFileLock):
        """Lock byte zero with ``LockFileEx``. A reader can keep the file on disk after release."""

        @override
        def _acquire(self) -> None:
            raise_on_not_writable_file(self._lock_path)

            # Check the opened handle so a concurrent rename cannot redirect the lock.
            try:
                fd = open_non_reparse_fd(self._lock_path, self._open_mode())
            except BlockingIOError:
                return
            if fd is None:
                return
            try:
                locked = lock_fd_nonblocking(fd)
                if locked:
                    self._mark_descriptor_owned(fd)
            except BaseException:
                # Closing the descriptor also drops a lock recorded before the interrupt.
                self._mark_descriptor_released()
                os.close(fd)
                raise
            if not locked:
                os.close(fd)

        @override
        def _release(self) -> None:
            fd = cast("int", self._context.lock_file_fd)
            # An unlock failure leaves the byte range held. Only report release after the kernel commits it.
            unlock_fd(fd)
            self._mark_descriptor_released()
            self._close_released_fd(fd, default_suppresses=False)
            if not self._settings.preserve_lock_file:
                with suppress(OSError):
                    unlink_without_oplock_wait(self._lock_path)

    def lock_fd_nonblocking(fd: int) -> bool:
        # Locking byte zero explicitly keeps reads and writes from changing the locked range.
        overlapped = _OVERLAPPED()
        flags: Final[int] = 0x02 | 0x01  # LOCKFILE_EXCLUSIVE_LOCK | LOCKFILE_FAIL_IMMEDIATELY
        if _KERNEL32.LockFileEx(msvcrt.get_osfhandle(fd), flags, 0, 1, 0, ctypes.byref(overlapped)):
            return True
        err = ctypes.get_last_error()
        error_lock_violation: Final[int] = 33
        if err == error_lock_violation:
            return False
        raise ctypes.WinError(err)  # pragma: no cover - other native failures require an invalid handle

    def unlock_fd(fd: int) -> None:
        overlapped = _OVERLAPPED()
        error_not_locked: Final[int] = 158
        if (  # pragma: no cover  # only an interrupted earlier release leaves our own range unlocked
            not _KERNEL32.UnlockFileEx(msvcrt.get_osfhandle(fd), 0, 1, 0, ctypes.byref(overlapped))
            and (err := ctypes.get_last_error()) != error_not_locked
        ):
            raise ctypes.WinError(err)

    __all__ = ["WindowsFileLock", "lock_fd_nonblocking", "unlock_fd"]
else:  # pragma: win32 no cover

    class WindowsFileLock(BaseFileLock):
        """Uses ``LockFileEx`` to hard lock a byte range of the lock file on Windows systems."""

        @override
        def _acquire(self) -> None:
            raise NotImplementedError

        @override
        def _release(self) -> None:
            raise NotImplementedError

    __all__ = ["WindowsFileLock"]
