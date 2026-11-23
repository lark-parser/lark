"""Cancel a blocked query pipe read on Windows."""

from __future__ import annotations

import sys
from time import monotonic
from typing import TYPE_CHECKING, Final

if sys.platform == "win32":
    from ctypes import WinDLL, WinError, get_last_error, wintypes

if TYPE_CHECKING:
    from threading import Thread


def stop_query_reader(reader: Thread) -> None:
    deadline = monotonic() + 1
    while reader.is_alive() and monotonic() < deadline:
        if (thread_id := reader.native_id) is not None:
            try:
                _cancel_synchronous_io(thread_id)
            except OSError:
                if reader.is_alive():
                    raise
        reader.join(0.05)
    if reader.is_alive():
        msg = "query output reader did not stop"
        raise TimeoutError(msg)


def _cancel_synchronous_io(thread_id: int) -> None:
    error_not_found: Final[int] = 1168
    kernel = WinDLL("kernel32", use_last_error=True)
    open_thread = kernel.OpenThread
    open_thread.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    open_thread.restype = wintypes.HANDLE
    cancel = kernel.CancelSynchronousIo
    cancel.argtypes = (wintypes.HANDLE,)
    cancel.restype = wintypes.BOOL
    close = kernel.CloseHandle
    close.argtypes = (wintypes.HANDLE,)
    close.restype = wintypes.BOOL

    if not (handle := open_thread(0x0001, wintypes.BOOL(0), thread_id)):
        raise WinError(get_last_error())
    try:
        if not cancel(handle) and (error := get_last_error()) != error_not_found:
            raise WinError(error)
    finally:
        if not close(handle):
            raise WinError(get_last_error())


__all__ = [
    "stop_query_reader",
]
