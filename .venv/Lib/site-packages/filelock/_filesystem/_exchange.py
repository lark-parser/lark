"""Atomic name exchange for removing or breaking lock files."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from importlib.machinery import ModuleSpec

__spec__ = cast("ModuleSpec", __spec__)

__lazy_modules__ = ["pathlib", "platform", "re", "secrets", f"{__spec__.parent}._files"]

import errno
import os
import platform
import re
import secrets
import stat
import sys
import time
from contextlib import contextmanager, suppress
from errno import EINVAL, ENOSPC, ENOSYS, EXDEV
from functools import cache
from pathlib import Path
from typing import Final

from ._files import write_all

if TYPE_CHECKING:
    import ctypes
    from collections.abc import Callable, Generator


_BREAK_HEADER: Final[str] = "filelock/break\n"


def break_marker_pid(content: str | None) -> int | None:
    if content is not None and (match := re.fullmatch(rf"{_BREAK_HEADER}([0-9]+)\n", content)):
        with suppress(ValueError):
            return int(match[1])
    return None


def remove_own_file(lock_file: str, fd: int) -> None:  # pragma: win32 no cover
    # The caller pins the inode until cleanup, so a successor cannot reuse its number.
    own: Final[os.stat_result] = os.fstat(fd)
    with suppress(FileNotFoundError):
        try:
            break_lock_file(lock_file, own.st_mtime, own.st_ino)
            if os.path.samestat(os.lstat(lock_file), own):
                Path(lock_file).unlink()
        except OSError as exc:
            if exc.errno == ENOSPC:
                # A sparse byte makes our failed marker reclaimable without allocating a data block.
                os.ftruncate(fd, 1)
            raise


def break_lock_file(lock_file: str, mtime_before: float, ino_before: int) -> None:
    # A peer may have replaced the observed marker, even on filesystems with coarse timestamps.
    if (current := os.lstat(lock_file)).st_mtime != mtime_before or current.st_ino != ino_before:
        return
    break_path: Final[str] = break_marker_path(lock_file, os.getpid())
    if exchange_supported():  # pragma: win32 no cover
        # Keep the lock path occupied while checking which marker the exchange displaced.
        fd: Final[int] = os.open(break_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        grabbed: os.stat_result | None = None
        try:
            try:
                with suppress(OSError):
                    write_break_marker(fd)
                    exchange_names(break_path, lock_file)
                grabbed = os.lstat(break_path)
            finally:
                # A signal can interrupt the exchange or the first identity check after the names have moved.
                if grabbed is None:
                    grabbed = os.lstat(break_path)
                if grabbed.st_mtime == mtime_before and grabbed.st_ino == ino_before:
                    Path(break_path).unlink()
                    if os.path.samestat(os.lstat(lock_file), os.fstat(fd)):
                        Path(lock_file).unlink()
                else:
                    exchange_back(lock_file, break_path, fd)
        finally:
            os.close(fd)
    elif _MOVES_WITHOUT_EXCHANGE:  # pragma: win32 cover
        # A hard link restores a live marker without overwriting a successor.
        with _pinned_for_rename(lock_file):
            Path(lock_file).rename(break_path)
        if (st_after := os.lstat(break_path)).st_mtime == mtime_before and st_after.st_ino == ino_before:
            unlink_path(break_path)
        elif stat.S_ISREG(st_after.st_mode) and hasattr(os, "link"):  # pragma: needs hard-link
            with suppress(OSError):
                os.link(break_path, lock_file, follow_symlinks=False)
                unlink_path(break_path)


def break_marker_path(lock_file: str, pid: int) -> str:
    return f"{lock_file}.break.{pid}.{secrets.token_hex(16)}"


def exchange_supported() -> bool:
    return _rename_call() is not None


@cache
def _rename_call() -> tuple[Callable[[bytes, bytes, int], int], int] | None:
    # Most callers never exchange markers and need no ctypes import.
    try:
        import ctypes  # ruff:ignore[import-outside-top-level]  # only a stale break needs it
    except ImportError:  # pragma: no cover  # GraalPy ships without ctypes
        return None
    if sys.platform in {"linux", "android"}:  # pragma: linux cover
        if (renameat2 := _renameat2(ctypes.CDLL(None, use_errno=True))) is None:
            return None  # pragma: no cover  # an architecture the CI matrix does not run
        return renameat2, 2  # RENAME_EXCHANGE in linux/fs.h
    if sys.platform == "darwin":  # pragma: darwin cover
        renamex_np = ctypes.CDLL(None, use_errno=True).renamex_np
        renamex_np.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        renamex_np.restype = ctypes.c_int

        def call_renamex_np(source: bytes, target: bytes, flags: int) -> int:
            return 0 if renamex_np(source, target, flags) == 0 else ctypes.get_errno()

        return call_renamex_np, 0x2  # RENAME_SWAP in sys/stdio.h
    return None  # pragma: linux no cover  # pragma: android no cover  # pragma: darwin no cover


def _renameat2(libc: ctypes.CDLL) -> Callable[[bytes, bytes, int], int] | None:  # pragma: linux cover
    # Older C libraries omit the wrapper even when the kernel supports renameat2.
    import ctypes  # ruff:ignore[import-outside-top-level]  # only a stale break needs it

    numbers: Final[dict[str, int]] = {
        "x86_64": 316,
        "i386": 353,
        "i686": 353,
        "armv7l": 382,
        "armv8l": 382,
        "aarch64": 276,
        "riscv64": 276,
        "loongarch64": 276,
        "ppc64le": 357,
        "s390x": 347,
    }
    if (number := numbers.get(platform.machine())) is None:
        return None  # pragma: no cover  # an architecture the CI matrix does not run
    syscall = libc.syscall
    syscall.restype = ctypes.c_long
    at_fdcwd = -100

    def call_renameat2(source: bytes, target: bytes, flags: int) -> int:
        arguments = (
            ctypes.c_long(number),
            ctypes.c_int(at_fdcwd),
            ctypes.c_char_p(source),
            ctypes.c_int(at_fdcwd),
            ctypes.c_char_p(target),
            ctypes.c_uint(flags),
        )
        return 0 if syscall(*arguments) == 0 else ctypes.get_errno()

    return call_renameat2


def write_break_marker(fd: int) -> None:
    write_all(fd, f"{_BREAK_HEADER}{os.getpid()}\n".encode("ascii"))


def exchange_names(source: str, target: str) -> bool:  # pragma: win32 no cover
    renamer, exchange_flag = cast("tuple[Callable[[bytes, bytes, int], int], int]", _rename_call())
    if not (error := renamer(os.fsencode(source), os.fsencode(target), exchange_flag)):
        return True
    # OverlayFS and FUSE can reject cross-layer exchanges with EXDEV.
    if error in {EINVAL, ENOSYS, EXDEV, getattr(errno, "ENOTSUP", EINVAL), getattr(errno, "EOPNOTSUPP", EINVAL)}:
        return False
    raise OSError(error, os.strerror(error), source, None, target)


def exchange_back(
    lock_file: str, aside: str, fd: int, *, unlink_settled_aside: bool = True
) -> bool:  # pragma: win32 no cover
    # Concurrent breakers can strand a live marker if they undo exchanges out of order.
    try:
        settled = _exchange_until_aside(lock_file, aside, os.fstat(fd))
    except FileNotFoundError:
        settled = True
    if settled and unlink_settled_aside:
        Path(aside).unlink(missing_ok=True)
    return settled


def _exchange_until_aside(lock_file: str, aside: str, own: os.stat_result) -> bool:  # pragma: win32 no cover
    # Peers need a few system calls to unwind; a paused or dead peer must not block the caller indefinitely.
    deadline: Final[float] = time.monotonic() + 2.0
    stall: Final[float] = 0.01
    feed_at = time.monotonic() + stall
    while not os.path.samestat(os.lstat(aside), own):
        now = time.monotonic()
        ours = os.path.samestat(os.lstat(lock_file), own)
        if not ours and now >= deadline:
            return False
        if ours or now >= feed_at:
            if not exchange_names(aside, lock_file):
                return False
            feed_at = now + stall
        else:
            time.sleep(0.0005)
    return True


if sys.platform == "win32":  # pragma: win32 cover
    from ._windows import cancelling_oplock_wait, open_for_delete_without_oplock_wait, unlink_without_oplock_wait

    @contextmanager
    def _pinned_for_rename(path: str) -> Generator[None]:
        # The open handles exclusive oplocks; a rename can still block on a reader's oplock.
        with os.fdopen(open_for_delete_without_oplock_wait(path), "rb"), cancelling_oplock_wait():
            yield

    unlink_path = unlink_without_oplock_wait

else:  # pragma: win32 no cover

    def unlink_path(path: str) -> None:
        Path(path).unlink()


_MOVES_WITHOUT_EXCHANGE: Final[bool] = sys.platform == "win32"


__all__ = [
    "break_lock_file",
    "break_marker_path",
    "break_marker_pid",
    "exchange_back",
    "exchange_names",
    "exchange_supported",
    "remove_own_file",
    "unlink_path",
    "write_break_marker",
]
