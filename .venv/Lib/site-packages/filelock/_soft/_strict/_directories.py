"""Validation and pinned access to strict soft-lock directories."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from importlib.machinery import ModuleSpec

__spec__ = cast("ModuleSpec", __spec__)

__lazy_modules__ = [
    "contextlib",
    "filelock._core",
    "filelock._filesystem",
    "functools",
    "itertools",
    "pathlib",
    "secrets",
    f"{__spec__.parent}._claims",
]

import contextlib
import functools
import itertools
import os
import secrets
import stat
import sys
from dataclasses import dataclass
from errno import EACCES, EPERM
from pathlib import Path
from typing import Final

from filelock._core import SoftFileLockProtocolError
from filelock._filesystem import foreign_owner, write_all

from ._claims import (
    CLAIM_DIRECTORY_NAME,
    TOKEN_HEX_LENGTH,
    ClaimEntryLimitError,
    RetryDoorwayError,
    claim_name,
    is_claim_probe_name,
    is_reclaimable_private_name,
    parse_claim_name,
    private_public_name,
    private_record_name,
)

if sys.platform == "win32":  # pragma: win32 cover
    from filelock._filesystem import DirectoryPinBlockedError, pin_directory, unpin_directory

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

# Binary mode prevents Windows newline translation in protocol records.
O_BINARY: Final[int] = getattr(os, "O_BINARY", 0)


# A replaced os function no longer compares equal to the original in os.supports_dir_fd.
@dataclass(frozen=True, slots=True, kw_only=True)
class _FileSupport:
    open_dir_fd: bool
    unlink_dir_fd: bool
    stat_dir_fd: bool
    link_dir_fd: bool
    link_follow_symlinks: bool
    scandir_fd: bool
    mkdir_dir_fd: bool
    has_link: bool


_HAS_LINK: Final[bool] = hasattr(os, "link")

SUPPORTS: Final[_FileSupport] = _FileSupport(
    open_dir_fd=os.open in os.supports_dir_fd,
    unlink_dir_fd=os.unlink in os.supports_dir_fd,
    stat_dir_fd=os.stat in os.supports_dir_fd,
    link_dir_fd=_HAS_LINK and os.link in os.supports_dir_fd,
    link_follow_symlinks=_HAS_LINK and os.link in os.supports_follow_symlinks,
    scandir_fd=os.scandir in os.supports_fd,
    mkdir_dir_fd=os.mkdir in os.supports_dir_fd,
    has_link=_HAS_LINK,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class _ScanLimits:
    claims: int
    entries: int
    read_grace: float


# Scans include private entries, but only public claims count toward the contention limit.
LIMITS: Final[_ScanLimits] = _ScanLimits(claims=1024, entries=16_384, read_grace=0.5)


def ensure_claim_directory(lock_file: str, directory: Path, mode: int) -> None:
    if not (SUPPORTS.open_dir_fd and SUPPORTS.mkdir_dir_fd):  # pragma: lacks dir-fd
        try:
            pinned = pin_directories(directory.parent, acquiring=True)
        except OSError as error:
            raise SoftFileLockProtocolError(lock_file, None, f"cannot open {directory.parent}") from error
        with pinned:
            ensure_protocol_directory(lock_file, directory, mode)
    else:  # pragma: needs dir-fd
        # mkdir follows a symlink in every component but the last, so create against a descriptor of the real parent.
        try:
            coordination_fd = open_directory(os.fspath(directory.parent))
        except OSError as error:
            raise SoftFileLockProtocolError(lock_file, None, f"cannot open {directory.parent}") from error
        try:
            if sys.platform != "win32":  # pragma: win32 no cover
                _refuse_unrelated_coordination_entries(lock_file, directory.parent, coordination_fd)
            ensure_protocol_directory(lock_file, directory, mode, coordination_fd)
        finally:
            with contextlib.suppress(OSError):
                os.close(coordination_fd)


def pin_directories(*directories: Path, acquiring: bool = False) -> contextlib.ExitStack[bool | None]:
    # Pinning keeps a Windows directory from being replaced by a junction.
    stack: contextlib.ExitStack[bool | None] = contextlib.ExitStack()
    if sys.platform == "win32":  # pragma: win32 cover
        with stack:
            for directory in directories:
                try:
                    pin = pin_directory(str(directory), wait_for_oplock=not acquiring)
                except DirectoryPinBlockedError as error:
                    raise RetryDoorwayError from error
                stack.callback(unpin_directory, pin)
            return stack.pop_all()
    return stack  # pragma: win32 no cover


def ensure_protocol_directory(lock_file: str, directory: Path, mode: int, parent_fd: int | None = None) -> None:
    try:
        if parent_fd is None:
            directory.mkdir(mode)
        else:  # pragma: needs dir-fd
            os.mkdir(directory.name, mode, dir_fd=parent_fd)
    except FileExistsError:
        try:
            found = lstat_relative((os.fspath(directory.parent), parent_fd), directory.name)
        except OSError as error:
            raise SoftFileLockProtocolError(lock_file, None, f"cannot inspect {directory}") from error
        if (
            not stat.S_ISDIR(found.st_mode)
            or getattr(found, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
        ):
            raise SoftFileLockProtocolError(lock_file, None, f"{directory} is not a real directory") from None
    # An inherited ACL can widen a directory. The sticky bit protects claims where other accounts can write.
    if sys.platform != "win32":  # pragma: win32 no cover
        try:
            fd = os.open(
                directory.name if parent_fd is not None else os.fspath(directory),
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=parent_fd,
            )
        except OSError as error:
            raise SoftFileLockProtocolError(lock_file, None, f"cannot open {directory}") from error
        try:
            found = _owned_protocol_directory(lock_file, directory, fd, parent_fd)
            if directory.name != CLAIM_DIRECTORY_NAME:
                _refuse_unrelated_coordination_entries(lock_file, directory, fd)
            _settle_opened_directory_mode(lock_file, directory, mode, fd, found)
        finally:
            os.close(fd)


def lstat_relative(directory_ref: tuple[str, int | None], name: str) -> os.stat_result:
    directory, directory_fd = directory_ref
    if directory_fd is not None and SUPPORTS.stat_dir_fd:  # pragma: needs dir-fd
        return os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    return Path(directory, name).lstat()


def _owned_protocol_directory(
    lock_file: str, directory: Path, fd: int, parent_fd: int | None
) -> os.stat_result:  # pragma: win32 no cover
    try:
        found = os.fstat(fd)
        parent = directory.parent.stat() if parent_fd is None else os.fstat(parent_fd)
    except OSError as error:
        raise SoftFileLockProtocolError(lock_file, None, f"cannot set the mode of {directory}") from error
    if (owner := foreign_owner(found, parent, fd=fd)) is not None:  # pragma: needs foreign-sticky-tmp
        reason = f"{directory} belongs to uid {owner}, not to this process's account or the parent's owner"
        raise SoftFileLockProtocolError(lock_file, None, reason)
    return found


def _settle_opened_directory_mode(
    lock_file: str, directory: Path, mode: int, fd: int, found: os.stat_result
) -> None:  # pragma: win32 no cover
    settled = found.st_mode & 0o7000 | found.st_mode & mode & 0o777 | stat.S_ISVTX
    if directory.name == CLAIM_DIRECTORY_NAME:
        _refuse_unrelated_claim_entries(lock_file, directory, fd)
    if sys.platform != "win32" and found.st_uid == os.geteuid() and settled != stat.S_IMODE(found.st_mode):
        try:
            os.fchmod(fd, settled)
        except OSError as error:
            raise SoftFileLockProtocolError(lock_file, None, f"cannot set the mode of {directory}") from error


def _refuse_unrelated_claim_entries(lock_file: str, directory: Path, fd: int) -> None:  # pragma: win32 no cover
    try:
        with scandir_relative((os.fspath(directory), fd)) as entries:
            names = [entry.name for entry in itertools.islice(entries, LIMITS.entries + 1)]
        foreign = next(
            (
                name
                for name in names[: LIMITS.entries]
                if parse_claim_name(name) is None
                and not is_claim_probe_name(name)
                and parse_claim_name(private_public_name(name) or "") is None
                and not (
                    name.startswith(".nfs")
                    and len(name) > len(".nfs")
                    and all(c in "0123456789abcdef" for c in name[4:])
                )
            ),
            None,
        )
    except OSError as error:
        raise SoftFileLockProtocolError(lock_file, None, f"cannot list {directory}") from error
    if foreign is not None:
        raise SoftFileLockProtocolError(lock_file, foreign, "unknown claim name or protocol version")
    private = [name for name in names[: LIMITS.entries] if name.startswith(".")]
    if len(names) > LIMITS.entries:
        raise SoftFileLockProtocolError(
            lock_file, None, str(ClaimEntryLimitError(os.fspath(directory), LIMITS.entries, len(private)))
        )
    if len(names) - len(private) > LIMITS.claims:
        directory_ref = os.fspath(directory), fd
        now = functools.cache(
            functools.partial(
                filesystem_now, directory_ref, claim_name("held", secrets.token_hex(TOKEN_HEX_LENGTH // 2))
            )
        )
        try:
            for name in private[: LIMITS.claims]:
                if is_reclaimable_private_name(name):
                    reclaim_private_record(directory_ref, name, now)
        except OSError as error:
            reason = f"cannot reclaim private claim records: {error.strerror or type(error).__name__}"
            raise SoftFileLockProtocolError(lock_file, None, reason) from error
        raise RetryDoorwayError


def scandir_relative(
    directory_ref: tuple[str, int | None],
) -> contextlib.AbstractContextManager[Iterator[os.DirEntry[str]]]:
    directory, directory_fd = directory_ref
    if directory_fd is not None and SUPPORTS.scandir_fd:  # pragma: needs dir-fd
        return os.scandir(directory_fd)
    return os.scandir(directory)  # pragma: lacks dir-fd


def filesystem_now(directory_ref: tuple[str, int | None], public_name: str) -> float | None:  # pragma: win32 no cover
    # Use the filesystem clock to age records across hosts. A private probe can be reclaimed after a crash.
    probe = private_record_name(public_name)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | O_BINARY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = open_relative(directory_ref, probe, flags, 0o600)
    except OSError:
        return None
    try:
        write_all(fd, b"\n")
        return os.fstat(fd).st_mtime
    except OSError:
        return None
    finally:
        with contextlib.suppress(OSError):
            os.close(fd)
        with contextlib.suppress(OSError):
            unlink_private_record_once(directory_ref, probe)


def open_relative(directory_ref: tuple[str, int | None], name: str, flags: int, mode: int) -> int:
    directory, directory_fd = directory_ref
    return (
        os.open(name, flags, mode, dir_fd=directory_fd)
        if directory_fd is not None
        else os.open(Path(directory, name), flags, mode)
    )


def unlink_private_record_once(  # pragma: win32 no cover
    directory_ref: tuple[str, int | None], private_name: str
) -> None:
    directory, directory_fd = directory_ref
    if directory_fd is not None and SUPPORTS.unlink_dir_fd:  # pragma: needs dir-fd
        os.unlink(private_name, dir_fd=directory_fd)
    else:
        Path(directory, private_name).unlink()


def reclaim_private_record(
    directory_ref: tuple[str, int | None], private_name: str, now: Callable[[], float | None]
) -> None:
    directory, directory_fd = directory_ref
    try:
        private_stat = (
            os.stat(private_name, dir_fd=directory_fd, follow_symlinks=False)
            if directory_fd is not None and SUPPORTS.stat_dir_fd
            else Path(directory, private_name).lstat()
        )
    except FileNotFoundError:
        return
    if not stat.S_ISREG(private_stat.st_mode):
        msg = f"{Path(directory, private_name)} is not a regular private record"
        raise OSError(msg)
    # Closing a delete handle can wait indefinitely for another process's read-handle oplock.
    if sys.platform != "win32":  # pragma: win32 no cover
        private_record_grace: Final[float] = 2.0
        if private_stat.st_nlink == 1 and (
            (current := now()) is None or current - private_stat.st_mtime < private_record_grace
        ):
            return
        try:
            unlink_private_record_once(directory_ref, private_name)
        except FileNotFoundError:
            pass
        except OSError as error:
            if error.errno not in {EACCES, EPERM}:
                raise


def open_directory(directory: str, dir_fd: int | None = None) -> int:  # pragma: needs dir-fd
    return os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0), dir_fd=dir_fd)


def _refuse_unrelated_coordination_entries(lock_file: str, directory: Path, fd: int) -> None:  # pragma: win32 no cover
    try:
        with scandir_relative((os.fspath(directory), fd)) as entries:
            claim_entry = next(entries, None)
            unrelated = claim_entry is not None and (
                claim_entry.name != CLAIM_DIRECTORY_NAME
                or not claim_entry.is_dir(follow_symlinks=False)
                or next(entries, None) is not None
            )
    except OSError as error:
        raise SoftFileLockProtocolError(lock_file, None, f"cannot list {directory}") from error
    if unrelated:
        raise SoftFileLockProtocolError(lock_file, None, f"{directory} holds entries that are not this lock's")
    if claim_entry is None:
        return
    try:
        claims_fd = open_directory(
            claim_entry.name if SUPPORTS.open_dir_fd else claim_entry.path,
            dir_fd=fd if SUPPORTS.open_dir_fd else None,
        )
    except OSError as error:
        raise SoftFileLockProtocolError(
            lock_file, claim_entry.name, f"cannot open {directory / claim_entry.name}"
        ) from error
    try:
        _refuse_unrelated_claim_entries(lock_file, directory / claim_entry.name, claims_fd)
    finally:
        os.close(claims_fd)


def relative_identity(directory_ref: tuple[str, int | None], name: str) -> tuple[int, int] | None:
    directory, directory_fd = directory_ref
    try:
        if directory_fd is not None and SUPPORTS.stat_dir_fd:  # pragma: needs dir-fd
            path_stat = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        else:  # pragma: win32 cover
            path_stat = Path(directory, name).lstat()
    except FileNotFoundError:
        return None
    return file_identity(path_stat)


def file_identity(st: os.stat_result) -> tuple[int, int]:
    return st.st_dev, st.st_ino


def open_claim_directory(directory: str) -> int:  # pragma: needs dir-fd
    # Opening both directories through descriptors keeps O_NOFOLLOW effective on both components.
    coordination_directory, name = os.path.split(directory)
    coordination_fd = open_directory(coordination_directory)
    try:
        return open_directory(name, coordination_fd)
    finally:
        # The walk wrote nothing through it, and an error here would leak the descriptor this function returns.
        with contextlib.suppress(OSError):
            os.close(coordination_fd)


def pin_claim_directory(directory: Path, *, acquiring: bool = False) -> contextlib.ExitStack[bool | None]:
    return pin_directories(directory.parent, directory, acquiring=acquiring)


__all__ = [
    "LIMITS",
    "O_BINARY",
    "SUPPORTS",
    "ensure_claim_directory",
    "ensure_protocol_directory",
    "file_identity",
    "filesystem_now",
    "lstat_relative",
    "open_claim_directory",
    "open_directory",
    "open_relative",
    "pin_claim_directory",
    "pin_directories",
    "reclaim_private_record",
    "relative_identity",
    "scandir_relative",
    "unlink_private_record_once",
]
