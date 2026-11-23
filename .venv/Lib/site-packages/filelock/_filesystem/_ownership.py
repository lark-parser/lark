"""File ownership checks across user namespaces."""

from __future__ import annotations

__lazy_modules__ = ["pathlib", "platform"]

import os
import platform
import stat
import sys
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


def foreign_owner(node: os.stat_result, parent: os.stat_result, *, fd: int | None = None) -> int | None:
    # Under a sticky parent the file owner can replace the lock during a hold.
    if sys.platform != "win32" and parent.st_mode & stat.S_ISVTX:  # pragma: needs foreign-sticky-tmp
        owner = node.st_uid
        euid = os.geteuid()
        if owner not in {euid, parent.st_uid}:
            return owner
        if sys.platform in {"linux", "android"}:  # pragma: win32 no cover  # pragma: darwin no cover
            if not _linux_uid_is_unambiguous(owner, fd if owner == euid else None):
                return owner
    return None


def _linux_uid_is_unambiguous(owner: int, fd: int | None) -> bool:  # pragma: linux cover
    try:
        if owner != int(Path("/proc/sys/kernel/overflowuid").read_text(encoding="ascii")):
            return True
    except (OSError, ValueError):
        pass  # The configured overflow UID could match any owner in the sysctl's range.
    if fd is None:
        return False
    return ((probe := _linux_owner_probe()) is not None and probe(fd)) or _owner_is_mapped(fd)


@cache
def _linux_owner_probe() -> Callable[[int], bool] | None:  # pragma: linux cover
    try:
        import ctypes  # ruff:ignore[import-outside-top-level]  # only ambiguous Linux UIDs need these calls

        libc = ctypes.CDLL(None, use_errno=True)
    except (ImportError, OSError):
        return None
    noatime = getattr(os, "O_NOATIME", 0)
    if not noatime or not all(hasattr(libc, name) for name in ("fstatfs", "capget", "fcntl")):
        return None
    statfs = libc.fstatfs
    statfs.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_long)]
    libc.fcntl.argtypes = [ctypes.c_int, ctypes.c_int]
    capget = libc.capget
    capget.argtypes = [ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint32)]

    # Linux statfs starts with a native word except on s390x, where it starts with a 32-bit int. On little-endian
    # systems all filesystem magic numbers fit in the first four bytes of either layout.
    width = 4 if sys.byteorder == "little" or platform.machine() == "s390x" else ctypes.sizeof(ctypes.c_long)

    def caller_owns_fd(fd: int) -> bool:
        # The buffer includes the unused fields after the filesystem type, whose layout varies by architecture.
        info = (ctypes.c_long * 64)()
        if statfs(fd, info) != 0 or int.from_bytes(ctypes.string_at(info, width), sys.byteorder) not in {
            0x9123683E,  # Btrfs
            0xEF53,  # ext2, ext3, ext4
            0x794C7630,  # OverlayFS
            0x01021994,  # tmpfs
            0x58465342,  # XFS
        }:
            return False
        # capget version 3 returns two sets of effective, permitted and inheritable bits for the calling thread.
        header = (ctypes.c_uint32 * 2)(0x20080522, 0)
        caps = (ctypes.c_uint32 * 6)()
        if capget(header, caps) != 0 or caps[0] & (1 << 3):  # CAP_FOWNER bypasses the owner check.
            return False
        # Linux checks the kernel inode owner when O_NOATIME is first set. These descriptors are private until their
        # ownership check completes. Restore the flags before a caller's on_acquired callback can see the descriptor.
        flags = libc.fcntl(fd, 3)  # F_GETFL
        if flags < 0 or flags & noatime or libc.fcntl(fd, 4, ctypes.c_int(flags | noatime)) < 0:
            return False
        if libc.fcntl(fd, 4, ctypes.c_int(flags)) < 0:  # F_SETFL
            raise OSError(error := ctypes.get_errno(), os.strerror(error))
        return True

    return caller_owns_fd


def _owner_is_mapped(fd: int) -> bool:  # pragma: win32 no cover  # pragma: darwin no cover
    # A descriptor can outlive its mount's entry in mountinfo. Require its own mount ID before trusting the UID.
    proc = Path("/proc/thread-self")
    try:
        if (proc / "uid_map").read_bytes().split() != [b"0", b"0", b"4294967295"]:
            return False
        mount = next(
            line.split()[1]
            for line in (proc / "fdinfo" / str(fd)).read_bytes().splitlines()
            if line.startswith(b"mnt_id:")
        )
        with (proc / "mountinfo").open("rb") as mounts:
            # A stacked filesystem can report an owner translated by an idmapped backing mount.
            return any(
                line.startswith(mount + b" ")
                and b"idmapped" not in line.split(None, 6)[5].split(b",")
                and line.partition(b" - ")[2].partition(b" ")[0] in {b"btrfs", b"ext4", b"tmpfs", b"xfs"}
                for line in mounts
            )
    except (OSError, IndexError, StopIteration):
        return False


__all__ = [
    "foreign_owner",
]
