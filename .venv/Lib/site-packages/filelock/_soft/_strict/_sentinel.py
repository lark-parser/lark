"""Creation and inspection of the sentinel at the strict lock path."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from importlib.machinery import ModuleSpec

__spec__ = cast("ModuleSpec", __spec__)

__lazy_modules__ = [
    "filelock._core",
    "filelock._identity",
    "functools",
    "itertools",
    f"{__spec__.parent}._claims",
    f"{__spec__.parent}._directories",
    f"{__spec__.parent}._publication",
    f"{__spec__.parent}._scan",
]

import functools
import itertools
import os
import stat
import time
from errno import EEXIST
from types import MappingProxyType
from typing import Final, Literal, NamedTuple

from filelock._core import SoftFileLockProtocolError
from filelock._identity import describe_host_name, owner_is_stale
from filelock._soft import MALFORMED_LOCK_AGE_THRESHOLD, STRICT_SOFT_SENTINEL_RECORD, parse_lock_holder, parse_marker

from ._claims import CLAIM_RECORD_LIMIT, PrivateRecordReclaimedError, private_public_name
from ._directories import LIMITS, filesystem_now, reclaim_private_record
from ._publication import publish_record, raise_if_hard_links_unsupported
from ._scan import CLAIM_READ_RETRY, open_record

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

_OccupantState = Literal["sentinel", "held", "breaking", "exited", "damaged", "unparsable"]


_NODE_DESCRIPTIONS: Final[MappingProxyType[int, str]] = MappingProxyType({
    stat.S_IFDIR: "a directory",
    stat.S_IFLNK: "a symlink",
})


_LEGACY_SENTINEL: Final[bytes] = STRICT_SOFT_SENTINEL_RECORD.encode()


def open_or_create_sentinel(
    lock_file: str, path: Path, mode: int, unchanged_for: Callable[[os.stat_result], float]
) -> int | None:
    try:
        return _open_sentinel(lock_file, path, unchanged_for)
    except FileNotFoundError:
        pass

    _reclaim_sentinel_private_records(lock_file, path)
    try:
        publication_cleanup_error = publish_record(os.fspath(path), _LEGACY_SENTINEL, mode)
    except PrivateRecordReclaimedError:
        return None
    except (NotImplementedError, OSError) as error:
        raise_if_hard_links_unsupported(lock_file, error)
        if not isinstance(error, OSError) or error.errno != EEXIST:
            raise
    else:
        if publication_cleanup_error is not None:  # pragma: needs dir-fd
            raise publication_cleanup_error
    try:
        return _open_sentinel(lock_file, path, unchanged_for)
    except FileNotFoundError:
        return None


def _open_sentinel(lock_file: str, path: Path, unchanged_for: Callable[[os.stat_result], float]) -> int | None:
    # A new soft marker can still be empty while its owner writes it.
    deadline: float | None = None
    while True:
        fd, state, occupant = inspect_lock_path(path)
        if fd is not None or state == "held":
            return fd
        reason = f"expected the strict sentinel at the lock path, found {occupant}"
        if state == "unparsable":
            if unchanged_for(path.lstat()) < MALFORMED_LOCK_AGE_THRESHOLD:
                return None
            raise SoftFileLockProtocolError(
                lock_file, None, f"{reason}, unchanged for {MALFORMED_LOCK_AGE_THRESHOLD:g} seconds"
            )
        if deadline is None:
            deadline = time.monotonic() + 0.5
        if state == "breaking" and time.monotonic() >= deadline:
            return None
        if state == "exited" or time.monotonic() >= deadline:
            raise SoftFileLockProtocolError(lock_file, None, reason)
        time.sleep(CLAIM_READ_RETRY)


def inspect_lock_path(path: Path) -> _LockPathInspection:
    if not stat.S_ISREG(mode := path.lstat().st_mode):
        return _LockPathInspection(None, "damaged", _NODE_DESCRIPTIONS.get(stat.S_IFMT(mode), "a special file"))
    try:
        fd, record = open_record((os.fspath(path.parent), None), path.name, CLAIM_RECORD_LIMIT)
    except FileNotFoundError:
        raise
    except BlockingIOError as error:
        return _LockPathInspection(None, "breaking", f"a file it cannot read ({error.strerror or error})")
    except PermissionError as error:
        # Another account or a Windows sharing mode may deny a read of a live marker.
        return _LockPathInspection(None, "held", f"a file it cannot read ({error.strerror or error})")
    except OSError as error:
        return _LockPathInspection(None, "damaged", f"a file it cannot read ({error.strerror or error})")
    if record == _LEGACY_SENTINEL:
        return _LockPathInspection(fd, "sentinel", "the strict sentinel")
    os.close(fd)
    return _LockPathInspection(None, *_describe_soft_marker(record.decode("utf-8", errors="replace")))


class _LockPathInspection(NamedTuple):
    fd: int | None
    state: _OccupantState
    occupant: str


def _describe_soft_marker(content: str) -> tuple[_OccupantState, str]:
    # An inferred owner death cannot authorize removing a strict claim.
    if (record := parse_marker(content)) is not None:
        pid, hostname, start = record.pid, record.hostname, record.start
    elif (holder := parse_lock_holder(content)) is not None:
        pid, hostname, start = holder
    else:
        return "unparsable", "a file that is neither the sentinel nor a soft-lock marker it can parse"
    shown = describe_host_name(hostname)
    if owner_is_stale(pid, hostname, start):
        return "exited", f"a soft-lock marker left by pid {pid} on {shown}, which has exited"
    return "held", f"a soft-lock marker held by pid {pid} on {shown}"


def _reclaim_sentinel_private_records(lock_file: str, path: Path) -> None:
    directory_ref = os.fspath(path.parent), None
    now = functools.cache(functools.partial(filesystem_now, directory_ref, path.name))
    try:
        with os.scandir(path.parent) as entries:
            private = (entry.name for entry in entries if private_public_name(entry.name) == path.name)
            for name in itertools.islice(private, LIMITS.claims):
                reclaim_private_record(directory_ref, name, now)
    except OSError as error:
        reason = f"cannot reclaim sentinel private records: {error.strerror or error}"
        raise SoftFileLockProtocolError(lock_file, None, reason) from error


__all__ = [
    "inspect_lock_path",
    "open_or_create_sentinel",
]
