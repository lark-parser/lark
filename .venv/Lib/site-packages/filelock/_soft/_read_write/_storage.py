"""Filesystem access and holder record encoding for the generation log."""

from __future__ import annotations

__lazy_modules__ = [
    "filelock._filesystem",
    "filelock._identity",
    "filelock._soft",
    "itertools",
    "math",
    "pathlib",
    "secrets",
]

import errno
import os
import secrets
import stat
import sys
import time
from abc import abstractmethod
from contextlib import contextmanager, suppress
from errno import ELOOP, EMLINK, ENOENT, ENOTDIR, ENXIO, ESTALE
from itertools import islice
from math import isfinite
from pathlib import Path
from typing import TYPE_CHECKING, Final, Protocol

from filelock._core import override
from filelock._filesystem import (
    ensure_directory_exists,
    foreign_owner,
    write_all,
)
from filelock._identity import host_name
from filelock._soft import link_no_follow, pin_directories, raise_if_hard_links_unsupported

if TYPE_CHECKING:
    from collections.abc import Generator

PROTOCOL: Final[str] = "filelock-rw/1"
GENERATIONS_DIRECTORY: Final[str] = "gen"
HOLDERS_DIRECTORY: Final[str] = "holders"
TEMPORARY_PREFIX: Final[str] = ".commit-"
MAX_RECORD_SIZE: Final[int] = 1 << 20
MAX_LISTED_NAMES: Final[int] = 1 << 16
HOUSEKEEPING_BATCH: Final[int] = 1 << 8
_TOKEN_HEX_LENGTH: Final[int] = 32


_O_NOFOLLOW: Final[int] = getattr(os, "O_NOFOLLOW", 0)
# Probe once because a replaced os.rename loses its capability identity.
_SUPPORTS_DIR_FD: Final[bool] = (
    hasattr(os, "link")
    and {os.link, os.open, os.stat, os.mkdir, os.rename, os.unlink} <= os.supports_dir_fd
    and os.scandir in os.supports_fd
)
# Windows text mode would rewrite protocol newlines.
_O_BINARY: Final[int] = getattr(os, "O_BINARY", 0)
# NFS can return ESTALE after a peer unlinks an entry.
_MISSING_ERRNOS: Final[frozenset[int]] = frozenset({ENOENT, ESTALE})


class RecordFiles(Protocol):
    @abstractmethod
    def read(self, path: str) -> bytes | None: ...

    @abstractmethod
    def create(self, path: str, data: bytes, *, durable: bool = False) -> tuple[int, int]: ...

    @abstractmethod
    def link(self, source: str, target: str) -> bool: ...

    @abstractmethod
    def write_head(self, path: str, temporary: str, data: bytes) -> None: ...

    @abstractmethod
    def overwrite(self, path: str, data: bytes, identity: tuple[int, int], header: bytes) -> bool: ...

    @abstractmethod
    def unlink(self, path: str, *, witness: str | None = None) -> None: ...

    @abstractmethod
    def listdir(self, path: str) -> list[str]: ...

    @abstractmethod
    def prepare(self, root: str, *, force: bool = False) -> None: ...


class OsFiles(RecordFiles):
    def __init__(self, lock_file: str) -> None:
        self._lock_file = lock_file
        self._lock_parent = Path(lock_file).parent
        self._prepared = False

    @override
    def read(self, path: str) -> bytes | None:
        # A FIFO can block the initial open before fstat checks its type.
        if (fd := self._open(path, os.O_RDONLY | _O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0) | _O_BINARY)) is None:
            return None
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                return b""
            chunks: list[bytes] = []
            remaining = MAX_RECORD_SIZE + 1
            while remaining > 0 and (chunk := os.read(fd, remaining)):
                chunks.append(chunk)
                remaining -= len(chunk)
            return b"".join(chunks)
        finally:
            os.close(fd)

    def _open(self, path: str, flags: int) -> int | None:
        # Windows can report a sharing violation while a record is being deleted.
        deadline: float | None = None
        while True:
            if isinstance(opened := self._attempt_open(path, flags), int):
                return opened
            if opened.errno in _MISSING_ERRNOS:
                return None
            if not isinstance(opened, PermissionError) or sys.platform != "win32":
                raise opened
            if deadline is None:  # pragma: win32 cover
                deadline = time.monotonic() + 0.5
            elif time.monotonic() >= deadline:  # pragma: win32 cover
                return None
            time.sleep(0.002)  # pragma: win32 cover

    def _attempt_open(self, path: str, flags: int) -> int | OSError:
        try:
            with self._relative(path) as (name, dir_fd):
                return os.open(name, flags, dir_fd=dir_fd)
        except OSError as error:
            return error

    @contextmanager
    def _relative(self, path: str, depth: int = 2) -> Generator[tuple[str, int | None]]:
        directory, name = os.path.split(path)
        with self._directory(directory, depth) as dir_fd:
            yield (path if dir_fd is None else name), dir_fd

    @contextmanager
    def _directory(self, path: str, depth: int = 2) -> Generator[int | None]:
        # O_NOFOLLOW covers only the last component. Anchor both protocol directories on every access.
        if not depth:
            yield None
            return
        if _SUPPORTS_DIR_FD:  # pragma: needs link-dir-fd
            with self._relative(path, depth - 1) as (name, parent_fd):
                try:
                    fd = os.open(name, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | _O_NOFOLLOW, dir_fd=parent_fd)
                except OSError as error:
                    # NetBSD and FreeBSD report different errors for a symlink opened with O_NOFOLLOW.
                    if error.errno not in {ELOOP, EMLINK, ENOTDIR, getattr(errno, "EFTYPE", ELOOP)}:
                        raise
                    msg = f"{path} is not a directory or is a symlink; refusing to use it"
                    raise TreeReplacedError(msg) from error
                try:
                    self._admit(fd, path, parent_fd)
                except BaseException:
                    os.close(fd)
                    raise
            try:
                yield fd
            finally:
                os.close(fd)
        else:
            # Windows pins directories against rename. Other platforms here must check ownership by name.
            directories = [Path(path), *Path(path).parents][:depth][::-1]
            try:
                pins = pin_directories(*directories)
            except NotADirectoryError as error:  # pragma: win32 cover
                msg = f"{error.filename} is not a directory or is a symlink; refusing to use it"
                raise TreeReplacedError(msg) from error
            with pins:
                lock_directory = self._lock_parent.stat()
                for directory in directories:  # pragma: needs foreign-sticky-tmp
                    _raise_if_untrusted_directory(
                        str(directory), directory.lstat(), directory.parent.stat(), lock_directory
                    )
                yield None

    def _admit(self, fd: int, path: str, parent_fd: int | None) -> None:  # pragma: needs link-dir-fd
        # Inode reuse invalidates any cached ownership check.
        found = os.fstat(fd)
        parent = os.fstat(parent_fd) if parent_fd is not None else Path(path).parent.stat()
        _raise_if_untrusted_directory(path, found, parent, self._lock_parent.stat(), fd=fd)

    @override
    def create(self, path: str, data: bytes, *, durable: bool = False) -> tuple[int, int]:
        with self._relative(path) as (name, dir_fd):
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _O_NOFOLLOW | _O_BINARY, 0o600, dir_fd=dir_fd)
        try:
            write_all(fd, data)
            if durable:
                os.fsync(fd)
            created = os.fstat(fd)
        except BaseException:
            os.close(fd)
            # Only this call owns the temporary name.
            self.unlink(path)
            raise
        os.close(fd)
        return created.st_dev, created.st_ino

    @override
    def unlink(self, path: str, *, witness: str | None = None) -> None:
        try:
            with self._relative(path) as (name, dir_fd):
                if witness is not None:
                    os.stat(witness if dir_fd is None else Path(witness).name, dir_fd=dir_fd, follow_symlinks=False)
                os.unlink(name, dir_fd=dir_fd)
        except OSError as error:
            # Windows may keep an open record until its holder exits. A later sweep retries.
            if error.errno not in _MISSING_ERRNOS and not isinstance(error, PermissionError):
                raise

    @override
    def link(self, source: str, target: str) -> bool:
        failure: NotImplementedError | OSError | None = None
        # Pin both names in the same directory so a log reset cannot carry an old snapshot into the new log.
        with self._relative(source) as (source_name, directory):
            target_name = target if directory is None else Path(target).name
            try:
                link_no_follow(source_name, target_name, src_dir_fd=directory, dst_dir_fd=directory)
            except FileExistsError:
                pass
            except (NotImplementedError, OSError) as error:
                raise_if_hard_links_unsupported(self._lock_file, error)
                failure = error
            # NFS can report a committed link as failed after retransmission. The inode identifies the winner.
            if (identity := _identity(source_name, directory)) is not None and identity == _identity(
                target_name, directory
            ):
                return True
        if failure is not None:
            raise failure
        return False

    @override
    def write_head(self, path: str, temporary: str, data: bytes) -> None:
        with self._relative(path) as (name, directory):
            stage = temporary if directory is not None else str(Path(path).with_name(temporary))
            renamed = False
            fd = os.open(stage, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _O_NOFOLLOW | _O_BINARY, 0o600, dir_fd=directory)
            try:
                try:
                    write_all(fd, data)
                finally:
                    os.close(fd)
                os.replace(stage, name, src_dir_fd=directory, dst_dir_fd=directory)
                renamed = True
            finally:
                if not renamed:
                    with suppress(FileNotFoundError, PermissionError):
                        os.unlink(stage, dir_fd=directory)

    @override
    def overwrite(self, path: str, data: bytes, identity: tuple[int, int], header: bytes) -> bool:
        # Opening a FIFO for the header check can fail with ENXIO.
        try:
            fd = self._open(path, os.O_RDWR | _O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0) | _O_BINARY)
        except OSError as error:
            if error.errno != ENXIO:
                raise
            return False
        if fd is None:
            return False
        try:
            # Holder records have one name. A second link can point at an unrelated file on a reused inode.
            opened = os.fstat(fd)
            if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != identity or opened.st_nlink != 1:
                return False
            # A replacement can also reuse the inode with one link. Its header identifies the original record.
            remaining = header
            while remaining:
                if not (chunk := os.read(fd, len(remaining))) or not remaining.startswith(chunk):
                    return False
                remaining = remaining[len(chunk) :]
            os.lseek(fd, 0, os.SEEK_SET)
            write_all(fd, data)
        finally:
            os.close(fd)
        return True

    @override
    def listdir(self, path: str) -> list[str]:
        try:
            with self._directory(path) as dir_fd, os.scandir(path if dir_fd is None else dir_fd) as entries:
                return [entry.name for entry in islice(entries, MAX_LISTED_NAMES + 1)]
        except FileNotFoundError:
            return []

    @override
    def prepare(self, root: str, *, force: bool = False) -> None:
        if self._prepared and not force:
            return
        ensure_directory_exists(root)
        for directory, depth in (
            (Path(root), 0),
            (Path(root, GENERATIONS_DIRECTORY), 1),
            (Path(root, HOLDERS_DIRECTORY), 1),
        ):
            with self._relative(str(directory), depth) as (name, dir_fd), suppress(FileExistsError):
                os.mkdir(name, 0o700, dir_fd=dir_fd)
            # mkdir has no O_NOFOLLOW and an existing entry could be a symlink.
            with self._directory(str(directory), depth + 1):
                pass
        self._prepared = True


class TreeReplacedError(RuntimeError):
    pass


def _raise_if_untrusted_directory(
    path: str, found: os.stat_result, parent: os.stat_result, lock_directory: os.stat_result, *, fd: int | None = None
) -> None:
    if not stat.S_ISDIR(found.st_mode) or getattr(found, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
        msg = f"{path} is not a directory or is a symlink; refusing to use it"
        raise TreeReplacedError(msg)
    for above in dict.fromkeys((parent, lock_directory)):
        if (owner := foreign_owner(found, above, fd=fd)) is not None:  # pragma: needs foreign-sticky-tmp
            msg = f"{path} belongs to uid {owner}, not to this process's account or the parent's owner"
            raise TreeReplacedError(msg)
        if above.st_mode & stat.S_ISVTX and found.st_mode & (stat.S_IWGRP | stat.S_IWOTH):  # pragma: win32 no cover
            msg = f"{path} is writable by other accounts; refusing to use it"
            raise TreeReplacedError(msg)


def _identity(path: str, dir_fd: int | None) -> tuple[int, int] | None:
    try:
        st = os.stat(path, dir_fd=dir_fd, follow_symlinks=False)
    except OSError:
        return None
    return st.st_dev, st.st_ino


def encode_holder(token: str, nonce: str, lease: float) -> bytes:
    # A peer with a shorter lease must still respect the writer's refresh interval.
    return holder_header(token) + (
        f"pid={os.getpid()}\nhost={host_name()}\nlease={float(lease)!r}\nnonce={nonce}\n"
    ).encode("ascii")


def holder_header(token: str) -> bytes:
    return f"{PROTOCOL}\ntoken={token}\n".encode("ascii")


def holder_lease(record: bytes | None) -> float | None:
    try:
        text = next(
            line for line in (record or b"").decode("ascii").split("\n") if line.startswith("lease=")
        ).removeprefix("lease=")
        lease = float(text)
    except (StopIteration, ValueError):  # UnicodeDecodeError is a ValueError
        return None
    # Accept only the spelling written by the holder.
    return lease if isfinite(lease) and lease > 0 and repr(lease) == text else None


def new_token() -> str:
    return secrets.token_hex(_TOKEN_HEX_LENGTH // 2)


def is_token(value: str) -> bool:
    return len(value) == _TOKEN_HEX_LENGTH and all(character in "0123456789abcdef" for character in value)


__all__ = [
    "GENERATIONS_DIRECTORY",
    "HOLDERS_DIRECTORY",
    "HOUSEKEEPING_BATCH",
    "MAX_LISTED_NAMES",
    "MAX_RECORD_SIZE",
    "PROTOCOL",
    "TEMPORARY_PREFIX",
    "OsFiles",
    "RecordFiles",
    "TreeReplacedError",
    "encode_holder",
    "holder_header",
    "holder_lease",
    "is_token",
    "new_token",
]
