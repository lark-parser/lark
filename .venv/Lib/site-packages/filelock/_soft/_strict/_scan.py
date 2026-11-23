"""Directory scans and validation of published strict soft-lock claims."""

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
    "pathlib",
    "secrets",
    f"{__spec__.parent}._claims",
    f"{__spec__.parent}._directories",
    f"{__spec__.parent}._publication",
]

import contextlib
import functools
import os
import secrets
import stat
import sys
import time
from errno import ENOENT, EPERM, ESTALE
from pathlib import Path
from typing import Final

from filelock._core import SoftFileLockProtocolError, raise_cleanup_errors

from ._claims import (
    CLAIM_PROBE_PREFIX,
    CLAIM_RECORD_LIMIT,
    PRIVATE_RECORD_SUFFIX,
    TOKEN_HEX_LENGTH,
    ClaimEntryLimitError,
    RetryDoorwayError,
    StrictSoftFileClaim,
    StrictSoftFileClaimState,
    claim_name,
    is_reclaimable_private_name,
    parse_claim,
    parse_claim_name,
)
from ._directories import (
    LIMITS,
    O_BINARY,
    SUPPORTS,
    file_identity,
    filesystem_now,
    lstat_relative,
    open_claim_directory,
    open_relative,
    pin_claim_directory,
    reclaim_private_record,
    scandir_relative,
)
from ._publication import link_or_find_committed, unlink_relative

if sys.platform == "win32":  # pragma: win32 cover
    from filelock._filesystem import is_unlinked, open_deletable_for_reading, open_read_without_oplock_wait

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

CLAIM_READ_RETRY: Final[float] = 0.002


def read_existing_claims(
    lock_file: str,
    directory: Path,
    *,
    entry_limit: int | None,
    verify_server: bool = sys.platform != "win32",
) -> tuple[StrictSoftFileClaim, ...]:
    if not SUPPORTS.open_dir_fd:  # pragma: lacks dir-fd
        try:
            pinned = pin_claim_directory(directory, acquiring=entry_limit is not None)
        except FileNotFoundError:
            return ()
        except OSError as error:
            reason = f"cannot open claim directory: {error.strerror or type(error).__name__}"
            raise SoftFileLockProtocolError(lock_file, None, reason) from error
        with pinned:
            return _read_claims(
                lock_file, (os.fspath(directory), None), entry_limit=entry_limit, verify_server=verify_server
            )
    try:  # pragma: needs dir-fd
        directory_fd = open_claim_directory(os.fspath(directory))
    except FileNotFoundError:  # pragma: needs dir-fd
        return ()
    except OSError as error:  # pragma: needs dir-fd
        reason = f"cannot open claim directory: {error.strerror or type(error).__name__}"
        raise SoftFileLockProtocolError(lock_file, None, reason) from error
    try:  # pragma: needs dir-fd
        return _read_claims(
            lock_file, (os.fspath(directory), directory_fd), entry_limit=entry_limit, verify_server=verify_server
        )
    finally:  # pragma: needs dir-fd
        with contextlib.suppress(OSError):
            os.close(directory_fd)


def _read_claims(
    lock_file: str, directory_ref: tuple[str, int | None], *, entry_limit: int | None, verify_server: bool
) -> tuple[StrictSoftFileClaim, ...]:
    names: Final[list[str]] = _list_claim_names(lock_file, directory_ref, entry_limit=entry_limit)
    name_parts: dict[str, tuple[StrictSoftFileClaimState, str]] = {}
    for name in names:
        if (parts := parse_claim_name(name)) is None:
            raise SoftFileLockProtocolError(lock_file, name, "unknown claim name or protocol version")
        name_parts[name] = parts
    records: Final[dict[str, bytes]] = _read_claim_records(lock_file, directory_ref, names, entry_limit=entry_limit)
    return tuple(
        parse_claim(lock_file, name, name_parts[name], records[name])
        for name in names
        if name in records and (not verify_server or _claim_exists_on_server(lock_file, directory_ref, name))
    )


def _list_claim_names(lock_file: str, directory_ref: tuple[str, int | None], *, entry_limit: int | None) -> list[str]:
    try:
        with scandir_relative(directory_ref) as entries:
            return _public_claim_names(lock_file, directory_ref, entries, entry_limit=entry_limit)
    except OSError as error:
        if error.errno == ESTALE and entry_limit is not None:
            raise RetryDoorwayError from error
        reason = f"cannot list claim directory: {error.strerror or type(error).__name__}"
        raise SoftFileLockProtocolError(lock_file, None, reason) from error


def _public_claim_names(
    lock_file: str,
    directory_ref: tuple[str, int | None],
    entries: Iterator[os.DirEntry[str]],
    *,
    entry_limit: int | None,
) -> list[str]:
    names: list[str] = []
    now: Callable[[], float | None] = (
        functools.cache(
            functools.partial(
                filesystem_now, directory_ref, claim_name("held", secrets.token_hex(TOKEN_HEX_LENGTH // 2))
            )
        )
        if entry_limit is not None
        else lambda: None
    )
    reclaims = hidden = 0
    for scanned, entry in enumerate(entries):
        if entry_limit is not None and scanned >= entry_limit:
            raise ClaimEntryLimitError(directory_ref[0], scanned, hidden)
        if not entry.name.startswith("."):
            names.append(entry.name)
            if entry_limit is not None and len(names) > LIMITS.claims:
                _refuse_excess_claims(lock_file, names)
            continue
        hidden += 1
        if reclaims < LIMITS.claims and is_reclaimable_private_name(entry.name):
            reclaims += 1
            reclaim_private_record(directory_ref, entry.name, now)
    return sorted(names)


def _refuse_excess_claims(lock_file: str, names: list[str]) -> None:
    for name in names:
        if parse_claim_name(name) is None:
            raise SoftFileLockProtocolError(lock_file, name, "unknown claim name or protocol version")
    raise RetryDoorwayError


def _read_claim_records(
    lock_file: str, directory_ref: tuple[str, int | None], names: list[str], *, entry_limit: int | None
) -> dict[str, bytes]:
    # Windows deletion and NFS revalidation can delay a read. One deadline bounds the whole scan.
    records: dict[str, bytes] = {}
    deadline: float | None = None
    while True:
        pending: dict[str, OSError] = {}
        for name in names:
            record, error = _attempt_claim_read(lock_file, directory_ref, name)
            if error is not None:
                pending[name] = error
            elif record is not None:
                records[name] = record
        if not pending:
            return records
        if deadline is None:
            deadline = time.monotonic() + LIMITS.read_grace
        elif time.monotonic() >= deadline:
            break
        names = list(pending)
        time.sleep(CLAIM_READ_RETRY)
    # After revalidation, ESTALE identifies a name the NFS server no longer has.
    if denied := [name for name, error in pending.items() if error.errno != ESTALE]:
        # Windows can deny opens after a peer removes the claim from the directory.
        listed: Final[set[str]] = set(_list_claim_names(lock_file, directory_ref, entry_limit=entry_limit))
        if still_listed := [name for name in denied if name in listed]:
            error = pending[still_listed[0]]
            reason = f"cannot read claim: {error.strerror or str(error) or type(error).__name__}"
            raise SoftFileLockProtocolError(lock_file, still_listed[0], reason) from error
    return records


def _attempt_claim_read(
    lock_file: str, directory_ref: tuple[str, int | None], name: str
) -> tuple[bytes | None, OSError | None]:
    try:
        fd, record = open_record(directory_ref, name, CLAIM_RECORD_LIMIT, deletable=True)
        os.close(fd)
    except FileNotFoundError:
        return None, None
    except PermissionError as error:
        if sys.platform == "win32" and is_unlinked(str(Path(directory_ref[0], name))):  # pragma: win32 cover
            return None, None
        return None, error
    except OSError as error:
        if error.errno == ESTALE:
            return None, error
        reason = f"cannot read claim: {error.strerror or str(error) or type(error).__name__}"
        raise SoftFileLockProtocolError(lock_file, name, reason) from error
    else:
        return record, None


def open_record(
    directory_ref: tuple[str, int | None], name: str, limit: int, *, deletable: bool = False
) -> tuple[int, bytes]:
    path = Path(directory_ref[0], name)
    path_stat = lstat_relative(directory_ref, name)
    if not stat.S_ISREG(path_stat.st_mode):
        msg = f"{path} is not a regular file"
        raise OSError(msg)
    if deletable and sys.platform == "win32":  # pragma: win32 cover
        # A claim's owner must be able to unlink it while another process reads it.
        fd = open_deletable_for_reading(str(path))
    elif sys.platform == "win32":  # pragma: win32 cover
        # The sentinel stays for the lock's lifetime, so its handle shares no delete.
        fd = open_read_without_oplock_wait(str(path), share_delete=False)
    else:  # pragma: win32 no cover
        flags = os.O_RDONLY | O_BINARY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        fd = open_relative(directory_ref, name, flags, 0)
    try:
        record = _read_opened_record(fd, path, path_stat, limit)
    except BaseException as read_error:  # preserve read and descriptor cleanup errors
        try:
            os.close(fd)
        except BaseException as close_error:  # ruff:ignore[blind-except]  # preserve read and descriptor cleanup errors
            raise_cleanup_errors("strict record read cleanup failed", read_error, close_error)
        raise
    return fd, record


def _read_opened_record(fd: int, path: Path, path_stat: os.stat_result, limit: int) -> bytes:
    opened_stat = os.fstat(fd)
    if not stat.S_ISREG(opened_stat.st_mode):
        msg = f"{path} is not a regular file"
        raise OSError(msg)
    if file_identity(opened_stat) != file_identity(path_stat):
        msg = f"{path} changed while opening"
        raise OSError(msg)
    record = os.read(fd, limit + 1)
    if len(record) > limit:
        msg = f"{path} exceeds {limit} bytes"
        raise OSError(msg)
    return record


def _claim_exists_on_server(lock_file: str, directory_ref: tuple[str, int | None], name: str) -> bool:
    # NFS may cache a vanished name. A hard link checks whether the server still has it.
    proof = f"{CLAIM_PROBE_PREFIX}{secrets.token_hex(TOKEN_HEX_LENGTH // 2)}{PRIVATE_RECORD_SUFFIX}"
    try:
        link_or_find_committed(directory_ref, name, proof)
    except OSError as error:
        if error.errno in {ENOENT, ESTALE}:
            return False
        if error.errno == EPERM:
            # Linux may refuse a hard link to another account's claim; it still counts as held.
            return True
        reason = f"cannot verify claim: {error.strerror or type(error).__name__}"
        raise SoftFileLockProtocolError(lock_file, name, reason) from error
    except NotImplementedError as error:
        raise SoftFileLockProtocolError(lock_file, name, "cannot verify claim: hard links unavailable") from error
    try:
        unlink_relative(directory_ref, proof)
    except FileNotFoundError:
        pass
    except OSError as error:
        reason = f"cannot remove claim probe: {error.strerror or type(error).__name__}"
        raise SoftFileLockProtocolError(lock_file, name, reason) from error
    return True


__all__ = [
    "CLAIM_READ_RETRY",
    "open_record",
    "read_existing_claims",
]
