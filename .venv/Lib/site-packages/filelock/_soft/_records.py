"""Owner record formats for soft lock markers."""

from __future__ import annotations

__lazy_modules__ = ["contextlib", "filelock._filesystem", "math"]

import math
import os
import re
import stat
import sys
from contextlib import suppress
from typing import Final, Literal, NamedTuple

from filelock._filesystem import open_into

if sys.platform == "win32":  # pragma: win32 cover
    from filelock._filesystem import open_read_without_oplock_wait

#: Legacy contenders must leave a strict lock under the control of its claims directory.
STRICT_SOFT_SENTINEL_RECORD: Final[str] = "1\nfilelock-strict-v1\x00\n0\n"
#: Seconds a contender must observe an unchanged malformed record before reclaiming it.
MALFORMED_LOCK_AGE_THRESHOLD: Final[float] = 2.0
_MAX_LOCK_FILE_SIZE: Final[int] = 1024
_PROTOCOL: Final[str] = "filelock/2"
_DURATION: Final[re.Pattern[str]] = re.compile(
    r"""
    [0-9]+             # decimal digits
    (?:\.[0-9]+)?      # the fractional part of a float repr
    (?:e[+-][0-9]+)?   # repr includes the sign of the exponent
    """,
    re.ASCII | re.VERBOSE,
)
#: Unknown modes preserve markers written by newer versions.
OwnerMode = Literal["lease", "exclusive", "unknown"]


def read_lock_file(path: str) -> tuple[str | None, os.stat_result]:
    # Inspect non-regular nodes without following symlinks or blocking on FIFOs.
    st = os.lstat(path)
    if not stat.S_ISREG(st.st_mode):  # pragma: needs fifo
        return None, st
    # A different node may have replaced the marker since lstat.
    opened: list[int] = []
    try:
        if sys.platform == "win32":  # pragma: win32 cover
            # A blocking open can wait for an oplock past the acquisition deadline.
            opened.extend(map(open_read_without_oplock_wait, (path,)))
        else:  # pragma: win32 no cover
            open_into(opened, path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0), 0)
        fd = opened[0]
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):  # pragma: no cover  # only a non-regular node swapped in after the lstat
            return None, st
        data = os.read(fd, _MAX_LOCK_FILE_SIZE + 1)
    finally:
        for fd in opened:
            os.close(fd)
    if len(data) <= _MAX_LOCK_FILE_SIZE:
        with suppress(UnicodeDecodeError):
            return data.decode("utf-8"), st
    return None, st


def parse_lock_holder(content: str | None) -> _LockHolder | None:
    # A missing newline means a partial write. Its incomplete host or token cannot establish ownership.
    if not content or not content.endswith("\n") or len(lines := content.strip().splitlines()) not in {2, 3}:
        return None
    start_token_line_count: Final[int] = 3
    try:
        pid = parse_decimal(lines[0])
        start_token = parse_decimal(lines[2]) if len(lines) == start_token_line_count else None
    except ValueError:
        return None
    # Out-of-range PIDs can denote process groups or overflow the OS probe.
    if not 1 <= pid <= 2**31 - 1:
        return None
    return _LockHolder(pid, lines[1], start_token)


def parse_decimal(text: str) -> int:
    if not (text.isascii() and text.isdigit()):
        msg = f"not a decimal integer: {text!r}"
        raise ValueError(msg)
    return int(text)


class _LockHolder(NamedTuple):
    pid: int
    hostname: str
    start_token: int | None


def parse_marker(content: str | None) -> OwnerRecord | None:
    # An incomplete final line may look like an unknown mode that peers must preserve.
    if not content or content[-1] != "\n" or not (lines := content.strip().splitlines()) or lines[0] != _PROTOCOL:
        return None
    fields: dict[str, str] = {}
    for line in lines[1:]:
        key, separator, value = line.partition("=")
        if not separator:
            return None
        fields[key] = value
    return _build_record(fields)


def _build_record(fields: dict[str, str]) -> OwnerRecord | None:
    # Keep unknown modes so older contenders cannot reclaim a newer protocol's live marker.
    if (published := fields.get("mode")) is None:
        return None
    mode: Final[OwnerMode] = published if published in {"lease", "exclusive"} else "unknown"
    hostname = fields.get("host")
    if not hostname or "pid" not in fields or ("duration" in fields and not _DURATION.fullmatch(fields["duration"])):
        return None
    try:
        pid = parse_decimal(fields["pid"])
        duration = float(fields["duration"]) if "duration" in fields else None
        start = parse_decimal(fields["start"]) if "start" in fields else None
    except ValueError:
        return None
    if not 1 <= pid <= (2**31 - 1):
        return None
    token = fields.get("token")
    # A decimal duration can overflow to infinity even when its spelling is valid.
    if mode == "lease" and (not token or duration is None or not (math.isfinite(duration) and duration > 0)):
        return None
    return OwnerRecord(pid=pid, hostname=hostname, mode=mode, token=token, lease_duration=duration, start=start)


class OwnerRecord(NamedTuple):
    """
    Keep optional metadata when reading unknown lock modes.

    :param pid: the PID of the process that wrote the marker
    :param hostname: the host name recorded in the marker
    :param mode: the owner mode the marker declares: ``lease``, ``exclusive``, or ``unknown``
    :param token: the claim token of a lease, or ``None``
    :param lease_duration: the lease duration in seconds, or ``None`` when the marker records none
    :param start: the owner's process start token, or ``None`` when none was recorded
    """

    pid: int
    hostname: str
    mode: OwnerMode
    token: str | None = None
    lease_duration: float | None = None
    start: int | None = None


def encode_marker(record: OwnerRecord) -> bytes:
    lines = [_PROTOCOL, f"pid={record.pid}", f"host={record.hostname}", f"mode={record.mode}"]
    if record.token is not None:
        lines.append(f"token={record.token}")
    if record.lease_duration is not None:
        lines.append(f"duration={record.lease_duration!r}")
    if record.start is not None:
        lines.append(f"start={record.start}")
    return "".join(f"{line}\n" for line in lines).encode()


__all__ = [
    "MALFORMED_LOCK_AGE_THRESHOLD",
    "STRICT_SOFT_SENTINEL_RECORD",
    "OwnerMode",
    "OwnerRecord",
    "encode_marker",
    "parse_decimal",
    "parse_lock_holder",
    "parse_marker",
    "read_lock_file",
]
