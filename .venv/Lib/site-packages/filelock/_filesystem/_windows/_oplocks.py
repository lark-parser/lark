"""Windows file operations that bound or avoid waits on opportunistic locks."""

from __future__ import annotations

__lazy_modules__ = ["msvcrt", "threading"]

import sys

if sys.platform == "win32":  # pragma: win32 cover
    import ctypes
    import msvcrt
    import os
    import threading
    import time
    from contextlib import ExitStack, contextmanager, suppress
    from ctypes import wintypes
    from errno import EEXIST
    from typing import TYPE_CHECKING, Final

    from ._handles import (
        CREATE_OPTIONS,
        DELETE,
        FILE_ATTRIBUTE_NORMAL,
        FILE_CREATE,
        FILE_OPEN,
        FILE_READ_ATTRIBUTES,
        FILE_SHARE_ALL,
        FILE_SHARE_READ_WRITE,
        GENERIC_READ,
        GENERIC_WRITE,
        INVALID_HANDLE_VALUE,
        KERNEL32,
        STATUS_OPLOCK_BREAK_IN_PROGRESS,
        STATUS_SUCCESS,
        SYNCHRONIZE,
        descriptor_for_non_reparse,
        nt_create,
        status_error,
        try_set_delete_disposition,
    )

    if TYPE_CHECKING:
        from collections.abc import Generator

    FILE_DELETE_ON_CLOSE: Final[int] = 0x00001000
    ERROR_OPERATION_ABORTED: Final[int] = 995
    DUPLICATE_SAME_ACCESS: Final[int] = 0x00000002
    STATUS_OBJECT_NAME_COLLISION: Final[int] = 0xC0000035
    KERNEL32.DuplicateHandle.argtypes = [
        wintypes.HANDLE,
        wintypes.HANDLE,
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.HANDLE),
        wintypes.DWORD,
        wintypes.BOOL,
        wintypes.DWORD,
    ]
    KERNEL32.DuplicateHandle.restype = wintypes.BOOL
    KERNEL32.CancelSynchronousIo.argtypes = [wintypes.HANDLE]
    KERNEL32.CancelSynchronousIo.restype = wintypes.BOOL
    KERNEL32.WriteFile.argtypes = [
        wintypes.HANDLE,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.c_void_p,
    ]
    KERNEL32.WriteFile.restype = wintypes.BOOL
    KERNEL32.ReOpenFile.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD]
    KERNEL32.ReOpenFile.restype = wintypes.HANDLE

    _ACCESS_DENIED_GRACE: Final[float] = 0.5

    @contextmanager
    def cancelling_oplock_wait(deadline: float | None = None) -> Generator[None]:
        """
        Request cancellation when a reader blocks synchronous I/O.

        :param deadline: monotonic deadline, or None for the default grace period
        :yields: control while the watchdog can cancel the current thread's I/O
        :raises WinError: duplicating the thread handle failed
        """
        # A reader can hold a rename indefinitely. Retry cancellation in case the first attempt precedes the syscall.
        thread = wintypes.HANDLE()
        process = KERNEL32.GetCurrentProcess()
        if not KERNEL32.DuplicateHandle(
            process,
            KERNEL32.GetCurrentThread(),
            process,
            ctypes.byref(thread),
            0,
            wintypes.BOOL(),
            DUPLICATE_SAME_ACCESS,
        ):  # pragma: no cover  # a thread may duplicate its own handle
            raise ctypes.WinError(ctypes.get_last_error())
        done = threading.Event()

        def cancel_until_done() -> None:
            while True:
                interval = _ACCESS_DENIED_GRACE
                if deadline is not None:
                    # A nonblocking attempt still needs time to enter the syscall.
                    interval = max(0.01, min(interval, deadline - time.perf_counter()))
                if done.wait(interval):
                    return
                KERNEL32.CancelSynchronousIo(thread)

        watchdog = threading.Thread(target=cancel_until_done, name="filelock-oplock-wait", daemon=True)
        with ExitStack() as cleanup:
            cleanup.callback(KERNEL32.CloseHandle, thread)
            cleanup.callback(lambda: watchdog.is_alive() and watchdog.join())
            cleanup.callback(done.set)
            # A finalizing interpreter may refuse to start the watchdog.
            with suppress(RuntimeError):  # pragma: no cover
                watchdog.start()
            yield

    def oplock_wait_cancelled(error: BaseException) -> bool:
        """
        Recognize the Windows error produced by a canceled I/O request.

        :param error: exception from the blocked operation
        :returns: whether Windows reported cancellation
        """
        return isinstance(error, OSError) and getattr(error, "winerror", None) == ERROR_OPERATION_ABORTED

    def open_read_without_oplock_wait(path: str, *, share_delete: bool = True) -> int:
        """
        Read a file without waiting for an oplock break.

        :param path: file to open
        :param share_delete: allow deletion while the descriptor is open
        :returns: read-only descriptor
        """
        sys.audit("open", path, None, os.O_RDONLY)
        share = FILE_SHARE_ALL if share_delete else FILE_SHARE_READ_WRITE
        return _open_existing_without_oplock_wait(path, GENERIC_READ | SYNCHRONIZE, os.O_RDONLY, share)

    def _open_existing_without_oplock_wait(path: str, access: int, flags: int, share: int = FILE_SHARE_ALL) -> int:
        handle, status = nt_create(path, access, FILE_ATTRIBUTE_NORMAL, share, FILE_OPEN)
        if status != STATUS_SUCCESS:
            raise status_error(status, path)
        return descriptor_for_non_reparse(handle, path, flags)

    def open_for_delete_without_oplock_wait(path: str) -> int:
        """
        Request delete access without waiting for an oplock break.

        :param path: file to open
        :returns: descriptor with delete access
        """
        # A read-handle oplock survives this open, so the caller still bounds the rename.
        return _open_existing_without_oplock_wait(path, DELETE | FILE_READ_ATTRIBUTES | SYNCHRONIZE, os.O_RDONLY)

    def create_exclusive_non_reparse_fd(path: str, opened: list[int]) -> int:
        """
        Create a marker without replacing an existing name.

        :param path: marker file name
        :param opened: empty list that receives the descriptor before an interrupt can strand it
        :returns: descriptor for the new marker
        :raises FileExistsError: the name is already occupied
        """
        # FILE_CREATE checks the final name, including a dangling symlink.
        sys.audit("open", path, None, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_TRUNC)
        raw = wintypes.HANDLE()
        try:
            handle, status = nt_create(
                path,
                GENERIC_WRITE | FILE_READ_ATTRIBUTES | SYNCHRONIZE,
                FILE_ATTRIBUTE_NORMAL,
                FILE_SHARE_READ_WRITE,
                FILE_CREATE,
                raw=raw,
            )
            if status == STATUS_OBJECT_NAME_COLLISION:
                raise FileExistsError(EEXIST, os.strerror(EEXIST), path)
            if status != STATUS_SUCCESS:
                raise status_error(status, path)
            # Record ownership before a pending signal can interrupt descriptor conversion.
            opened.extend(map(msvcrt.open_osfhandle, (handle,), (os.O_WRONLY | os.O_NOINHERIT,)))
        finally:
            if raw.value and not opened:
                _discard_created_marker(raw.value, path)
        return opened[0]

    def _discard_created_marker(handle: int, path: str) -> None:
        # Keep a pin across close so DELETE targets the marker we created.
        pins: list[int] = []
        deletes: list[int] = []
        try:
            try:
                # Leave a reclaimable marker if another reader denies deletion.
                KERNEL32.WriteFile(handle, b"\n", 1, ctypes.byref(wintypes.DWORD()), None)
                pins.extend(map(KERNEL32.ReOpenFile, (handle,), (0,), (FILE_SHARE_ALL,), (0,)))
            finally:
                KERNEL32.CloseHandle(handle)
            if pins[0] != INVALID_HANDLE_VALUE:
                with cancelling_oplock_wait():
                    deletes.extend(map(KERNEL32.ReOpenFile, pins, (DELETE,), (FILE_SHARE_ALL,), (0,)))
                    if deletes[0] != INVALID_HANDLE_VALUE:
                        sys.audit("os.remove", path, None)
                        try_set_delete_disposition(deletes[0])
        finally:
            for owned in (*deletes, *pins):
                if owned != INVALID_HANDLE_VALUE:
                    KERNEL32.CloseHandle(owned)

    def unlink_without_oplock_wait(path: str) -> None:
        """
        Delete the name on close, leaving it in place if an oplock blocks the open.

        :param path: name to remove
        """
        sys.audit("os.remove", path, None)
        handle, status = nt_create(
            path,
            DELETE | SYNCHRONIZE,
            FILE_ATTRIBUTE_NORMAL,
            FILE_SHARE_ALL,
            FILE_OPEN,
            options=CREATE_OPTIONS | FILE_DELETE_ON_CLOSE,
        )
        if status == STATUS_SUCCESS:
            KERNEL32.CloseHandle(handle)
        elif status != STATUS_OPLOCK_BREAK_IN_PROGRESS:
            raise status_error(status, path)

    __all__ = [
        "cancelling_oplock_wait",
        "create_exclusive_non_reparse_fd",
        "open_for_delete_without_oplock_wait",
        "open_read_without_oplock_wait",
        "oplock_wait_cancelled",
        "unlink_without_oplock_wait",
    ]
else:  # pragma: win32 no cover
    __all__ = []
