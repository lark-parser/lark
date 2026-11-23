"""Windows directory pins and access checks for private lock directories."""

from __future__ import annotations

__lazy_modules__ = ["struct"]

import sys

if sys.platform == "win32":  # pragma: win32 cover
    import ctypes
    import os
    import struct
    from contextlib import contextmanager
    from ctypes import wintypes
    from errno import ENOTDIR, EWOULDBLOCK
    from typing import TYPE_CHECKING, Final, cast

    from ._handles import (
        ADVAPI32,
        ERROR_ACCESS_DENIED,
        FILE_ATTRIBUTE_REPARSE_POINT,
        FILE_COMPLETE_IF_OPLOCKED,
        FILE_OPEN,
        FILE_OPEN_REPARSE_POINT,
        FILE_READ_ATTRIBUTES,
        FILE_SHARE_READ_WRITE,
        FILE_SYNCHRONOUS_IO_NONALERT,
        KERNEL32,
        NTDLL,
        STATUS_OPLOCK_BREAK_IN_PROGRESS,
        STATUS_SUCCESS,
        SYNCHRONIZE,
        ByHandleFileInformation,
        identity_of_handle,
        nt_create,
        owner_only_descriptor,
    )

    if TYPE_CHECKING:
        from collections.abc import Generator

    FILE_LIST_DIRECTORY: Final[int] = 0x00000001
    FILE_DIRECTORY_FILE: Final[int] = 0x00000001
    DIRECTORY_OPTIONS: Final[int] = FILE_SYNCHRONOUS_IO_NONALERT | FILE_DIRECTORY_FILE | FILE_OPEN_REPARSE_POINT

    class SecurityAttributes(ctypes.Structure):
        _fields_ = (
            ("nLength", wintypes.DWORD),
            ("lpSecurityDescriptor", ctypes.c_void_p),
            ("bInheritHandle", wintypes.BOOL),
        )

    ADVAPI32.GetNamedSecurityInfoW.argtypes = [
        wintypes.LPCWSTR,
        ctypes.c_int,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    ADVAPI32.GetNamedSecurityInfoW.restype = wintypes.DWORD
    ADVAPI32.OpenThreadToken.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.BOOL,
        ctypes.POINTER(wintypes.HANDLE),
    ]
    ADVAPI32.OpenThreadToken.restype = wintypes.BOOL
    ADVAPI32.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    ADVAPI32.OpenProcessToken.restype = wintypes.BOOL
    ADVAPI32.GetTokenInformation.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    ADVAPI32.GetTokenInformation.restype = wintypes.BOOL
    KERNEL32.LocalFree.argtypes = [ctypes.c_void_p]
    KERNEL32.LocalFree.restype = ctypes.c_void_p
    KERNEL32.CreateDirectoryW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(SecurityAttributes)]
    KERNEL32.CreateDirectoryW.restype = wintypes.BOOL

    class DirectoryPinBlockedError(BlockingIOError):
        """An oplock blocked a nonblocking directory pin."""

    def pin_directory(path: str, *, wait_for_oplock: bool = True) -> int:
        """
        Keep a directory from being renamed until its pin is released.

        :param path: directory to pin
        :param wait_for_oplock: wait for a conflicting oplock to break
        :returns: directory handle to pass to unpin_directory
        :raises DirectoryPinBlockedError: a conflicting oplock blocked a nonblocking pin
        :raises OSError: Windows refused to open the directory
        :raises WinError: querying the directory handle failed
        :raises NotADirectoryError: the directory is a junction or symlink
        """
        sys.audit("open", path, None, os.O_RDONLY)
        # Attribute access alone would permit a concurrent rename.
        access = FILE_LIST_DIRECTORY | FILE_READ_ATTRIBUTES | SYNCHRONIZE
        options = DIRECTORY_OPTIONS if wait_for_oplock else DIRECTORY_OPTIONS | FILE_COMPLETE_IF_OPLOCKED
        handle, status = nt_create(path, access, 0, FILE_SHARE_READ_WRITE, FILE_OPEN, options)
        if status == STATUS_OPLOCK_BREAK_IN_PROGRESS:
            raise DirectoryPinBlockedError(EWOULDBLOCK, "directory oplock break in progress", path)
        if status != STATUS_SUCCESS:
            winerror = NTDLL.RtlNtStatusToDosError(status)
            raise OSError(None, ctypes.FormatError(winerror).strip(), path, winerror)
        info = ByHandleFileInformation()
        # The handle was just opened with query access.
        if not KERNEL32.GetFileInformationByHandle(handle, ctypes.byref(info)):  # pragma: no cover
            error = ctypes.get_last_error()
            KERNEL32.CloseHandle(handle)
            raise ctypes.WinError(error)
        if info.dwFileAttributes & FILE_ATTRIBUTE_REPARSE_POINT:
            KERNEL32.CloseHandle(handle)
            raise NotADirectoryError(ENOTDIR, "is a junction or symlink, not a directory", path)
        return handle

    def unpin_directory(handle: int) -> None:
        """
        Allow renames after the final directory pin closes.

        :param handle: handle returned by pin_directory
        """
        KERNEL32.CloseHandle(handle)

    @contextmanager
    def pinned(path: str) -> Generator[tuple[int, int]]:
        """
        Keep the directory at its current path for the duration of the block.

        :param path: directory to pin
        :yields: volume serial number and file index
        """
        handle = pin_directory(path)
        try:
            yield identity_of_handle(handle)
        finally:
            unpin_directory(handle)

    def directory_is_private(path: str) -> bool:
        """
        Check the directory owner and inherited write permissions.

        :param path: directory to inspect
        :returns: whether only trusted accounts can modify the directory and its children
        :raises WinError: querying the security descriptor failed
        """
        # A directory owner can rewrite its ACL, and an inherited ACE can grant a child write access.
        owner, dacl, descriptor = ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_void_p()
        error = ADVAPI32.GetNamedSecurityInfoW(
            path,
            1,  # SE_FILE_OBJECT
            0x1 | 0x4,  # OWNER_SECURITY_INFORMATION | DACL_SECURITY_INFORMATION
            ctypes.byref(owner),
            None,
            ctypes.byref(dacl),
            None,
            ctypes.byref(descriptor),
        )
        if error == ERROR_ACCESS_DENIED:
            # An unreadable ACL cannot establish exclusive access.
            return False
        if error:  # pragma: no cover  # the directory was opened or listed an instant earlier
            raise ctypes.WinError(error)
        try:
            # CREATOR OWNER and OWNER RIGHTS refer to the owner when Windows applies the ACL.
            trusted = {_sid_from_text(text) for text in ("S-1-5-18", "S-1-5-32-544", "S-1-3-0", "S-1-3-4")}
            trusted.add(_user_sid())
            # A missing DACL grants everyone full access.
            return (
                bool(dacl.value)
                and _sid_at(cast("int", owner.value)) in trusted
                and _name_writers(cast("int", dacl.value)) <= trusted
            )
        finally:
            KERNEL32.LocalFree(descriptor)

    def _name_writers(dacl: int) -> set[bytes]:
        (count,) = struct.unpack("<4xH2x", ctypes.string_at(dacl, 8))
        writers = set()
        offset = 8
        for _ in range(count):
            ace_type, _flags, ace_size, mask = struct.unpack("<BBHI", ctypes.string_at(dacl + offset, 8))
            # Write access includes creating names, deleting children and changing the ACL or owner.
            if ace_type in {0, 9} and mask & (0x2 | 0x4 | 0x40 | 0x40000 | 0x80000 | 0x40000000 | 0x10000000):
                writers.add(_sid_at(dacl + offset + 8))
            offset += ace_size
        return writers

    def _user_sid() -> bytes:
        token = wintypes.HANDLE()
        token_query: Final[int] = 0x0008
        open_as_self: Final[bool] = True
        # The impersonated account determines who owns new names.
        if not (
            ADVAPI32.OpenThreadToken(KERNEL32.GetCurrentThread(), token_query, open_as_self, ctypes.byref(token))
            or ADVAPI32.OpenProcessToken(KERNEL32.GetCurrentProcess(), token_query, ctypes.byref(token))
        ):  # pragma: no cover  # every process may query its own token
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            size = wintypes.DWORD()
            ADVAPI32.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))
            buffer = ctypes.create_string_buffer(size.value)
            if not ADVAPI32.GetTokenInformation(
                token, 1, buffer, size, ctypes.byref(size)
            ):  # pragma: no cover  # the buffer has the size the first call asked for
                raise ctypes.WinError(ctypes.get_last_error())
            return _sid_at(cast("int", ctypes.c_void_p.from_buffer(buffer).value))
        finally:
            KERNEL32.CloseHandle(token)

    def _sid_from_text(text: str) -> bytes:
        revision, authority, *subauthorities = (int(part) for part in text.removeprefix("S-").split("-"))
        return (
            struct.pack("<BB", revision, len(subauthorities))
            + authority.to_bytes(6, "big")
            + struct.pack(f"<{len(subauthorities)}I", *subauthorities)
        )

    def _sid_at(address: int) -> bytes:
        return ctypes.string_at(address, 8 + 4 * ctypes.string_at(address + 1, 1)[0])

    def make_private_directory(path: str) -> None:
        """
        Create a directory writable only by the owner, administrators and SYSTEM.

        :param path: name for the new directory
        :raises WinError: Windows could not create the directory
        """
        attributes = SecurityAttributes(
            nLength=ctypes.sizeof(SecurityAttributes),
            lpSecurityDescriptor=owner_only_descriptor(),
            bInheritHandle=False,
        )
        if not KERNEL32.CreateDirectoryW(path, ctypes.byref(attributes)):  # pragma: no cover  # the name is fresh
            raise ctypes.WinError(ctypes.get_last_error())

    __all__ = [
        "DirectoryPinBlockedError",
        "directory_is_private",
        "make_private_directory",
        "pin_directory",
        "pinned",
        "unpin_directory",
    ]
else:  # pragma: win32 no cover
    __all__ = []
