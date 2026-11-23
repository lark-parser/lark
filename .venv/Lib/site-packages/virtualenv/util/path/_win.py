from __future__ import annotations

__lazy_modules__ = ["typing"]

import os
from typing import Final

if os.name == "nt":
    import ctypes
    from ctypes import wintypes


def get_short_path_name(long_name: str) -> str:
    """Gets the short path name of a given long path - http://stackoverflow.com/a/23598461/200291.

    :param long_name: the long path to shorten

    :returns: the short path name

    :raises WinError: an OSError when Windows cannot shorten the path

    """
    # ctypes.windll exists only on Windows, which is the only platform this runs on
    GetShortPathNameW = ctypes.windll.kernel32.GetShortPathNameW  # ruff:ignore[non-lowercase-variable-in-function]  # ty: ignore[missing-attribute]
    GetShortPathNameW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
    GetShortPathNameW.restype = wintypes.DWORD
    output_buf_size = 0
    while True:
        output_buf = ctypes.create_unicode_buffer(output_buf_size)
        needed = GetShortPathNameW(long_name, output_buf, output_buf_size)
        if needed == 0:
            raise ctypes.WinError()
        if output_buf_size >= needed:
            return output_buf.value
        output_buf_size = needed


if os.name == "nt":

    def delete_readonly(path: str) -> None:
        kernel: Final[ctypes.WinDLL] = ctypes.WinDLL("kernel32", use_last_error=True)
        create = kernel.CreateFileW
        create.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HANDLE,
        ]
        create.restype = wintypes.HANDLE
        get_info = kernel.GetFileInformationByHandleEx
        get_info.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
        get_info.restype = wintypes.BOOL
        set_info = kernel.SetFileInformationByHandle
        set_info.argtypes = get_info.argtypes
        set_info.restype = wintypes.BOOL
        close = kernel.CloseHandle
        close.argtypes = [wintypes.HANDLE]
        close.restype = wintypes.BOOL
        # Delete through the checked handle so another entry cannot replace the path.
        handle: Final[int | None] = create(path, 0x10180, 0x3, None, 3, 0x02200000, None)
        if handle == wintypes.HANDLE(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            info: Final[_FileBasicInfo] = _FileBasicInfo()
            if not get_info(handle, 0, ctypes.byref(info), ctypes.sizeof(info)):
                raise ctypes.WinError(ctypes.get_last_error())
            if info.attributes & 0x400:
                msg: Final[str] = f"refusing to change attributes of a reparse point: {path}"
                raise OSError(msg)
            # FileDispositionInfoEx can delete a read-only link without changing the file's attributes.
            disposition: Final[wintypes.DWORD] = wintypes.DWORD(0x11)
            if set_info(handle, 21, ctypes.byref(disposition), ctypes.sizeof(disposition)):
                return
            error: Final[int] = ctypes.get_last_error()
            if error not in {50, 87}:
                raise ctypes.WinError(error)
            # Some Windows filesystems and SMB shares reject the extended disposition, so a file with other links fails.
            _delete_readonly_legacy(path, handle, info, kernel)
        finally:
            close(handle)

    def _delete_readonly_legacy(path: str, handle: int, info: _FileBasicInfo, kernel: ctypes.WinDLL) -> None:
        get_info = kernel.GetFileInformationByHandleEx
        set_info = kernel.SetFileInformationByHandle
        standard: Final[_FileStandardInfo] = _FileStandardInfo()
        if not get_info(handle, 1, ctypes.byref(standard), ctypes.sizeof(standard)):
            raise ctypes.WinError(ctypes.get_last_error())
        if standard.number_of_links > 1:
            msg: Final[str] = f"cannot delete read-only hard link without changing its other names: {path}"
            raise OSError(msg)
        original_attributes: Final[int] = info.attributes
        info.attributes = (info.attributes & ~0x1) or 0x80
        if not set_info(handle, 0, ctypes.byref(info), ctypes.sizeof(info)):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            legacy_disposition: Final[ctypes.c_ubyte] = ctypes.c_ubyte(1)
            if not set_info(handle, 4, ctypes.byref(legacy_disposition), ctypes.sizeof(legacy_disposition)):
                raise ctypes.WinError(ctypes.get_last_error())
        except OSError:
            info.attributes = original_attributes
            if not set_info(handle, 0, ctypes.byref(info), ctypes.sizeof(info)):
                raise ctypes.WinError(ctypes.get_last_error()) from None
            raise

    class _FileBasicInfo(ctypes.Structure):
        _fields_: Final[list[tuple[str, type[ctypes.c_longlong | wintypes.DWORD]]]] = [
            ("creation", ctypes.c_longlong),
            ("access", ctypes.c_longlong),
            ("write", ctypes.c_longlong),
            ("change", ctypes.c_longlong),
            ("attributes", wintypes.DWORD),
        ]

    class _FileStandardInfo(ctypes.Structure):
        _fields_: Final[list[tuple[str, type[ctypes.c_longlong | wintypes.DWORD | ctypes.c_ubyte]]]] = [
            ("allocation_size", ctypes.c_longlong),
            ("end_of_file", ctypes.c_longlong),
            ("number_of_links", wintypes.DWORD),
            ("delete_pending", ctypes.c_ubyte),
            ("directory", ctypes.c_ubyte),
        ]


__all__ = (  # ruff:ignore[invalid-all-format]  # platform dependent
    ["delete_readonly", "get_short_path_name"] if os.name == "nt" else ["get_short_path_name"]
)
