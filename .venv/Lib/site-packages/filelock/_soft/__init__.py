"""Marker locks, leases and their shared record formats."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    assert __spec__ is not None

__lazy_modules__ = ["importlib", f"{__spec__.parent}._records"]

from importlib import import_module
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from ._records import (
    MALFORMED_LOCK_AGE_THRESHOLD,
    STRICT_SOFT_SENTINEL_RECORD,
    OwnerMode,
    OwnerRecord,
    encode_marker,
    parse_decimal,
    parse_lock_holder,
    parse_marker,
    read_lock_file,
)

if TYPE_CHECKING:
    from ._exclusive import MarkerSoftFileLock, SoftFileLock
    from ._lease import CompromiseReason, LeaseClaim, LeaseCompromise, LeaseHeartbeat, SoftFileLease
    from ._read_write import AsyncAcquireSoftReadWriteReturnProxy, AsyncSoftReadWriteLock, SoftReadWriteLock
    from ._strict import (
        StrictRelease,
        StrictSoftFileClaim,
        StrictSoftFileClaimState,
        StrictSoftFileLock,
        link_no_follow,
        pin_directories,
        raise_if_hard_links_unsupported,
    )

_EXPORTS: Final[MappingProxyType[str, str]] = MappingProxyType({
    "SoftFileLock": "._exclusive",
    "MarkerSoftFileLock": "._exclusive",
    "SoftFileLease": "._lease",
    "LeaseClaim": "._lease",
    "LeaseHeartbeat": "._lease",
    "LeaseCompromise": "._lease",
    "CompromiseReason": "._lease",
    "AsyncAcquireSoftReadWriteReturnProxy": "._read_write",
    "AsyncSoftReadWriteLock": "._read_write",
    "SoftReadWriteLock": "._read_write",
    "StrictRelease": "._strict",
    "StrictSoftFileClaim": "._strict",
    "StrictSoftFileClaimState": "._strict",
    "StrictSoftFileLock": "._strict",
    "link_no_follow": "._strict",
    "pin_directories": "._strict",
    "raise_if_hard_links_unsupported": "._strict",
})


def __getattr__(name: str) -> object:  # simplint: ignore[imprecise-annotation]  # class and type-alias exports
    # Loading an exclusive lock must not import the async reader/writer backend.
    if (module := _EXPORTS.get(name)) is None:
        raise AttributeError(name)
    return getattr(import_module(module, __name__), name)


__all__ = [
    "MALFORMED_LOCK_AGE_THRESHOLD",
    "STRICT_SOFT_SENTINEL_RECORD",
    "AsyncAcquireSoftReadWriteReturnProxy",
    "AsyncSoftReadWriteLock",
    "CompromiseReason",
    "LeaseClaim",
    "LeaseCompromise",
    "LeaseHeartbeat",
    "MarkerSoftFileLock",
    "OwnerMode",
    "OwnerRecord",
    "SoftFileLease",
    "SoftFileLock",
    "SoftReadWriteLock",
    "StrictRelease",
    "StrictSoftFileClaim",
    "StrictSoftFileClaimState",
    "StrictSoftFileLock",
    "encode_marker",
    "link_no_follow",
    "parse_decimal",
    "parse_lock_holder",
    "parse_marker",
    "pin_directories",
    "raise_if_hard_links_unsupported",
    "read_lock_file",
]
