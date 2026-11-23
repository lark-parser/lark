"""Publication and removal of owner markers."""

from __future__ import annotations

__lazy_modules__ = ["contextlib", "filelock._filesystem", "filelock._identity", "itertools", "pathlib", "typing"]

import os
import stat
import sys
import time
from abc import abstractmethod
from contextlib import suppress
from errno import EACCES, EBUSY, EEXIST, EPERM
from itertools import islice
from pathlib import Path
from typing import Final

from filelock._core import BaseFileLock, override, raise_grouped_errors
from filelock._filesystem import (
    open_into,
    raise_on_not_writable_file,
    remove_own_file,
    unlink_path,
    write_all,
    write_at_start,
)
from filelock._identity import host_name, process_start_token

if sys.platform == "win32":  # pragma: win32 cover
    from filelock._filesystem import create_exclusive_non_reparse_fd

_OTHERS_WRITE: Final[int] = stat.S_IWGRP | stat.S_IWOTH


class MarkerPublication(BaseFileLock):
    _marker_cleanup: tuple[int, int] | None = None
    _marker_fds: list[int]

    @override
    def _acquire(self) -> None:
        self._finish_marker_cleanup()
        raise_on_not_writable_file(self._lock_path)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_TRUNC
        if (o_nofollow := getattr(os, "O_NOFOLLOW", None)) is not None:  # pragma: needs o-nofollow
            flags |= o_nofollow
        # An interrupt before publication must leave the path free for the next contender.
        opened: Final[list[int]] = []
        identity: tuple[int, int] | None = None
        try:
            fd = self._create_marker(self._lock_path, flags, opened)
            identity = file_identity(os.fstat(fd))
            self._apply_explicit_mode(fd)
            self._write_lock_info(fd)
            self._mark_descriptor_owned(fd, identity)
        except BaseException as exception:
            if not opened:
                if not (
                    isinstance(exception, OSError)
                    and (exception.errno == EEXIST or (exception.errno == EACCES and sys.platform == "win32"))
                ):  # pragma: win32 no cover
                    raise
                self._try_break_stale_lock()
                return
            fd = opened[0]
            # A signal handler may have released the published descriptor already.
            if identity is not None and self._context.pending_lock_file_fd is None:
                raise
            self._mark_descriptor_released()
            try:
                if identity is None:
                    # Retry while the descriptor still pins the marker that Windows cleanup must identify.
                    with suppress(OSError):
                        identity = file_identity(os.fstat(fd))
                if sys.platform != "win32":  # pragma: win32 no cover
                    # The open descriptor prevents inode reuse during the identity check.
                    with suppress(OSError):
                        remove_own_file(self._lock_path, fd)
            finally:
                try:
                    os.close(fd)
                finally:
                    if sys.platform == "win32":  # pragma: win32 cover
                        self._unlink_held_marker(identity)
            raise

    def _finish_marker_cleanup(self) -> None:
        # Waiting would deadlock a reentrant caller. The gate holder finishes cleanup.
        if self._marker_cleanup is not None and self._transition_lock.acquire(blocking=False):  # pragma: win32 cover
            try:
                # The interrupted release owns this close error.
                with suppress(OSError):
                    self._close_marker_fd()
                if (identity := self._marker_cleanup) is not None:  # pragma: no branch  # the gate's holder clears it
                    self._windows_unlink_if_ours(identity)
            finally:
                self._transition_lock.release()

    def _close_marker_fd(self) -> None:  # pragma: win32 cover
        # Keep pop and close in C so an interrupt cannot make a retry close a recycled descriptor.
        try:
            list(map(os.close, islice(iter(self.__dict__.setdefault("_marker_fds", []).pop, None), 1)))
        except IndexError:
            return
        except OSError:
            if not self._suppresses_close_error(default_suppresses=False):
                raise

    def _windows_unlink_if_ours(self, identity: tuple[int, int]) -> None:  # pragma: win32 cover
        max_retries: Final[int] = 10
        retry_delay = 0.001
        for attempt in range(max_retries):
            # Windows can briefly deny unlink after close. A successor may take the name between retries.
            try:
                for name in self._marker_names():
                    with suppress(FileNotFoundError):
                        if file_identity(os.lstat(name)) == identity:
                            # Clear the pending ID before unlink because Windows may reuse it.
                            self._marker_cleanup = None
                            unlink_path(name)
                            break
            except OSError as exc:
                if exc.errno in {EACCES, EPERM}:
                    # A later acquire or release can retry the denied unlink.
                    self._marker_cleanup = identity
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay)
                        retry_delay *= 2
                    continue
            self._marker_cleanup = None
            return

    def _marker_names(self) -> tuple[str, ...]:
        # After a directory rename, the caller's relative path may still reach the marker.
        return tuple(dict.fromkeys((self._lock_path, self.lock_file)))

    def _create_marker(self, path: str, flags: int, opened: list[int]) -> int:
        if sys.platform == "win32":  # pragma: win32 cover
            fd = create_exclusive_non_reparse_fd(path, opened)
        else:  # pragma: win32 no cover
            fd = open_into(opened, path, flags, self._open_mode() & ~_OTHERS_WRITE)
        self._mark_descriptor_pending(fd)
        return fd

    def _apply_explicit_mode(self, fd: int) -> None:
        # An explicit mode must survive the umask.
        if self.has_explicit_mode and sys.platform != "win32":  # pragma: win32 no cover
            with suppress(PermissionError):
                os.fchmod(fd, self._context.mode & ~_OTHERS_WRITE)

    @staticmethod
    def _write_lock_info(fd: int) -> None:
        # A write failure must reach acquisition rollback before this marker counts as held.
        info = f"{os.getpid()}\n{host_name()}\n"
        if (token := process_start_token(os.getpid())) is not None:
            info += f"{token}\n"
        write_all(fd, info.encode())

    @abstractmethod
    def _try_break_stale_lock(self) -> None: ...

    def _unlink_held_marker(self, identity: tuple[int, int] | None) -> None:
        if sys.platform == "win32":  # pragma: win32 cover
            if identity is not None:
                self._windows_unlink_if_ours(identity)
        else:  # pragma: win32 no cover
            for name in self._marker_names():
                with suppress(FileNotFoundError, NotADirectoryError):
                    if file_identity(os.lstat(name)) == identity:
                        Path(name).unlink()
                        return

    @override
    def _release_current(self, *, force: bool) -> None:
        try:
            super()._release_current(force=force)
        finally:
            # A Windows release interrupted after close still owes the unlink.
            self._finish_marker_cleanup()

    @override
    def _release(self) -> None:
        fd = self._context.lock_file_fd
        assert fd is not None  # ruff:ignore[assert]  # _release runs only while held, so the descriptor is set
        # A signal handler may release after descriptor publication but before identity publication.
        identity = self._context.lock_file_fd_identity
        if identity is None:
            identity = file_identity(os.fstat(fd))
        if sys.platform == "win32":  # pragma: win32 cover
            self._release_then_unlink(fd, identity)
        else:  # pragma: win32 no cover
            # Unlink while the descriptor still prevents inode reuse.
            unlinked: Final[bool] = self._unlink_open_marker(fd, identity)
            # A failed close can recycle the descriptor number, so release ownership before closing.
            self._mark_descriptor_released()
            try:
                self._close_released_fd(fd, default_suppresses=False)
            finally:
                # Some filesystems allow unlink only after close.
                if not unlinked:
                    self._unlink_held_marker(identity)

    def _release_then_unlink(self, fd: int, identity: tuple[int, int]) -> None:  # pragma: win32 cover
        # The transition gate keeps another thread from overwriting a pending Windows unlink.
        with self._transition_lock:
            self._marker_fds = [fd]
            self._marker_cleanup = identity
            self._mark_descriptor_released()
            try:
                self._close_marker_fd()
            # Preserve both errors if cleanup fails while handling an interruption.
            except BaseException as close_error:
                try:
                    self._finish_marker_cleanup()
                except BaseException as cleanup_error:  # ruff:ignore[blind-except]  # keep control-flow failures
                    raise_grouped_errors(
                        "lock descriptor close and marker cleanup both failed",
                        close_error,
                        cleanup_error,
                    )
                raise
            self._finish_marker_cleanup()

    def _unlink_open_marker(self, fd: int, identity: tuple[int, int]) -> bool:  # pragma: win32 no cover
        replaced = False
        for name in self._marker_names():
            if (current := _marker_identity_at(name)) is None:
                continue
            if current != identity:
                replaced = True
                continue
            try:
                Path(name).unlink()
            except (FileNotFoundError, NotADirectoryError):
                continue
            except OSError as error:
                # A handler can raise after unlink succeeds. Keep the descriptor pinned until the name is checked.
                still_ours = _marker_identity_at(name) == identity
                if error.errno in {EACCES, EBUSY, EPERM}:
                    return not still_ours
                if not still_ours:
                    self._mark_descriptor_released()
                    self._close_released_fd(fd, default_suppresses=False)
                raise
            return True
        return not replaced or _retire_displaced_marker(fd)


def file_identity(st: os.stat_result) -> tuple[int, int]:
    return st.st_dev, st.st_ino


def _marker_identity_at(name: str) -> tuple[int, int] | None:  # pragma: win32 no cover
    try:
        return file_identity(os.lstat(name))
    except (FileNotFoundError, NotADirectoryError):
        return None


def _retire_displaced_marker(fd: int) -> bool:  # pragma: win32 no cover
    # A peer may restore this marker after exchange. Retire its live PID before truncating.
    released: Final[bytes] = b"filelock/released\n"
    try:
        write_at_start(fd, released)
        os.ftruncate(fd, len(released))
    except TimeoutError:
        raise
    except OSError:
        return False
    return True


__all__ = [
    "MarkerPublication",
    "file_identity",
]
