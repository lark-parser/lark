"""File and directory operations shared by lock backends."""

from __future__ import annotations

__lazy_modules__ = ["pathlib"]

import os
import stat
import sys
from contextlib import contextmanager
from errno import EACCES, EIO, EISDIR
from pathlib import Path
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Generator


def raise_on_not_writable_file(filename: str) -> None:
    try:
        # Inspect the directory entry itself because the subsequent open refuses symlinks.
        file_stat = os.lstat(filename)
    except OSError:
        return  # does not exist, or an error the caller cannot act on

    if stat.S_ISDIR(file_stat.st_mode):
        if sys.platform == "win32":  # pragma: win32 cover
            raise PermissionError(EACCES, "Permission denied", filename)
        raise IsADirectoryError(EISDIR, "Is a directory", filename)  # pragma: win32 no cover

    # ACLs and group permissions can allow writes without S_IWUSR.
    if not (file_stat.st_mode & stat.S_IWUSR) and not os.access(
        filename,
        os.W_OK,
        effective_ids=os.access in os.supports_effective_ids,
        follow_symlinks=os.access not in os.supports_follow_symlinks,
    ):
        try:
            os.lstat(filename)
        except FileNotFoundError:
            # A holder may unlink its marker between lstat() and access(); let the caller attempt creation.
            return
        raise PermissionError(EACCES, "Permission denied", filename)


def ensure_directory_exists(filename: Path | str) -> None:
    Path(filename).parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def pin_inode(lock_file: str) -> Generator[int | None]:
    # An open descriptor prevents a stale marker's inode from being reused during recovery.
    if sys.platform == "win32":  # pragma: win32 cover
        yield None
    else:  # pragma: win32 no cover
        # O_PATH can pin an unreadable file or a symlink without opening its target.
        flags = getattr(os, "O_PATH", os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)) | getattr(os, "O_NOFOLLOW", 0)
        opened: list[int] = []
        try:
            try:
                fd = open_into(opened, lock_file, flags, 0)
            except FileNotFoundError:
                raise
            except OSError:
                yield None
                return
            yield os.fstat(fd).st_ino
        finally:
            for fd in opened:
                os.close(fd)


def open_into(opened: list[int], path: str, flags: int, mode: int) -> int:  # pragma: win32 no cover
    # Record the new descriptor before Python can deliver a signal.
    opened.extend(map(os.open, (path,), (flags,), (mode,)))
    return opened[0]


def write_at_start(fd: int, data: bytes) -> None:  # pragma: win32 no cover
    if (pwrite := getattr(os, "pwrite", None)) is not None:
        pwrite(fd, data, 0)
    else:
        os.lseek(fd, 0, os.SEEK_SET)
        write_all(fd, data)


def write_all(fd: int, data: bytes) -> None:
    remaining = memoryview(data)
    while remaining:
        if (written := os.write(fd, remaining)) == 0:
            raise OSError(EIO, "os.write wrote 0 bytes before the record was complete")
        remaining = remaining[written:]


def touch(name: str, *, fd: int) -> None:
    if _SUPPORTS_UTIME_FD:  # pragma: needs utime-fd
        os.utime(fd, None)
        return
    os.utime(name, None, follow_symlinks=not _SUPPORTS_UTIME_NOFOLLOW)  # pragma: lacks utime-fd


_SUPPORTS_UTIME_FD: Final[bool] = sys.platform != "win32" and os.utime in os.supports_fd


_SUPPORTS_UTIME_NOFOLLOW: Final[bool] = os.utime in os.supports_follow_symlinks


__all__ = [
    "ensure_directory_exists",
    "open_into",
    "pin_inode",
    "raise_on_not_writable_file",
    "touch",
    "write_all",
    "write_at_start",
]
