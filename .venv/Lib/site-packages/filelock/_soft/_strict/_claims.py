"""Names and record formats for strict soft-lock claims."""

from __future__ import annotations

__lazy_modules__ = ["filelock._core", "filelock._identity", "secrets"]

import os
import secrets
from dataclasses import dataclass
from typing import Final, Literal, cast

from filelock._core import SoftFileLockProtocolError
from filelock._identity import host_name, process_start_token

#: An intent competes for the lock. A held claim records the winner.
StrictSoftFileClaimState = Literal["intent", "held"]
CLAIM_DIRECTORY_NAME: Final[str] = "claims"
_CLAIM_MAGIC: Final[str] = "filelock-strict-v1"
CLAIM_RECORD_LIMIT: Final[int] = 1024
TOKEN_HEX_LENGTH: Final[int] = 32
_PRIVATE_RECORD_MARKER: Final[str] = ".private-v1-"
PRIVATE_RECORD_SUFFIX: Final[str] = ".tmp"
_PRIVATE_RECORD_RANDOM_HEX_LENGTH: Final[int] = 32
CLAIM_PROBE_PREFIX: Final[str] = ".probe-v1-"


def is_reclaimable_private_name(name: str) -> bool:
    return is_claim_probe_name(name) or (
        (public_name := private_public_name(name)) is not None and parse_claim_name(public_name) is not None
    )


def is_claim_probe_name(name: str) -> bool:
    if not name.startswith(CLAIM_PROBE_PREFIX) or not name.endswith(PRIVATE_RECORD_SUFFIX):
        return False
    token = name[len(CLAIM_PROBE_PREFIX) : -len(PRIVATE_RECORD_SUFFIX)]
    return len(token) == TOKEN_HEX_LENGTH and all(character in "0123456789abcdef" for character in token)


def private_public_name(private_name: str) -> str | None:
    if not private_name.startswith(".") or not private_name.endswith(PRIVATE_RECORD_SUFFIX):
        return None
    public_name, marker, random_hex = private_name[1 : -len(PRIVATE_RECORD_SUFFIX)].rpartition(_PRIVATE_RECORD_MARKER)
    if (
        marker != _PRIVATE_RECORD_MARKER
        or len(random_hex) != _PRIVATE_RECORD_RANDOM_HEX_LENGTH
        or any(character not in "0123456789abcdef" for character in random_hex)
    ):
        return None
    return public_name


def parse_claim_name(name: str) -> tuple[StrictSoftFileClaimState, str] | None:
    if not name.endswith(".claim"):
        return None
    parts = name.removesuffix(".claim").split("-")
    claim_states: Final[frozenset[str]] = frozenset({"intent", "held"})
    claim_name_part_count: Final[int] = 3
    if len(parts) != claim_name_part_count or parts[0] not in claim_states or parts[1] != "v1":
        return None
    token = parts[2]
    if len(token) != TOKEN_HEX_LENGTH or any(character not in "0123456789abcdef" for character in token):
        return None
    return cast("StrictSoftFileClaimState", parts[0]), token


def parse_claim(
    lock_file: str,
    name: str,
    name_parts: tuple[StrictSoftFileClaimState, str],
    record: bytes,
) -> StrictSoftFileClaim:
    try:
        magic, token, pid_text, hostname_hex, start_text, trailing = record.decode("ascii").split("\n")
        pid = int(pid_text)
        start = int(start_text) if start_text else None
        hostname = bytes.fromhex(hostname_hex).decode("utf-8")
    except ValueError as error:
        raise SoftFileLockProtocolError(lock_file, name, "malformed claim record") from error
    if not all((
        not trailing,
        magic == _CLAIM_MAGIC,
        token == name_parts[1],
        1 <= pid <= 2**31 - 1,
        str(pid) == pid_text,
        start is None or (start >= 0 and str(start) == start_text),
        hostname.encode().hex() == hostname_hex
        and hostname.isprintable()
        and not any(character.isspace() for character in hostname),
    )):
        raise SoftFileLockProtocolError(lock_file, name, "malformed claim record")
    return StrictSoftFileClaim(name=name, state=name_parts[0], token=token, pid=pid, hostname=hostname, start=start)


@dataclass(frozen=True)
class StrictSoftFileClaim:
    """
    One parsed strict soft-lock claim.

    :param name: the claim's file name in the claim directory
    :param state: whether the claim is an ``intent`` or a ``held`` record
    :param token: the random token that identifies the claim
    :param pid: the PID of the process that wrote the claim
    :param hostname: the host name of the process that wrote the claim
    :param start: the owner's process start token, or ``None`` when the platform exposes no proven start time
    """

    name: str
    state: StrictSoftFileClaimState
    token: str
    pid: int
    hostname: str
    #: Optional process start token for identifying the owner during manual recovery.
    start: int | None = None


def claim_name(state: StrictSoftFileClaimState, token: str) -> str:
    return f"{state}-v1-{token}.claim"


class PrivateRecordReclaimedError(Exception):
    pass


def claim_record(token: str) -> bytes:
    hostname_hex = host_name().encode().hex()
    start = process_start_token(os.getpid())
    start_text = "" if start is None else str(start)
    return f"{_CLAIM_MAGIC}\n{token}\n{os.getpid()}\n{hostname_hex}\n{start_text}\n".encode("ascii")


def private_record_name(public_name: str) -> str:
    return f".{public_name}{_PRIVATE_RECORD_MARKER}{secrets.token_hex(_PRIVATE_RECORD_RANDOM_HEX_LENGTH // 2)}.tmp"


class RetryDoorwayError(Exception):
    pass


class ClaimEntryLimitError(RetryDoorwayError):
    def __str__(self) -> str:
        directory, read, hidden = self.args
        return f"{directory} exceeds the scan limit of {read} entries ({hidden} hidden entries in the first {read})"


__all__ = [
    "CLAIM_DIRECTORY_NAME",
    "CLAIM_PROBE_PREFIX",
    "CLAIM_RECORD_LIMIT",
    "PRIVATE_RECORD_SUFFIX",
    "TOKEN_HEX_LENGTH",
    "ClaimEntryLimitError",
    "PrivateRecordReclaimedError",
    "RetryDoorwayError",
    "StrictSoftFileClaim",
    "StrictSoftFileClaimState",
    "claim_name",
    "claim_record",
    "is_claim_probe_name",
    "is_reclaimable_private_name",
    "parse_claim",
    "parse_claim_name",
    "private_public_name",
    "private_record_name",
]
