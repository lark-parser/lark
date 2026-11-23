"""Hostnames for lock records and diagnostic messages."""

from __future__ import annotations

__lazy_modules__ = ["contextlib", "hashlib", "pathlib", "socket", "typing"]

import hashlib
import socket
import sys
from contextlib import suppress
from pathlib import Path
from typing import Final

_HOST_NAME_VERBATIM: Final[frozenset[int]] = frozenset(range(0x21, 0x7F)) - {ord("?")}
NAMESPACE_MARK: Final[str] = "?pidns-"


def host_name() -> str:
    # A namespace suffix separates containers that share a hostname but assign PIDs independently.
    initial_namespace: Final[int] = 0xEFFFFFFC  # Linux reserves this inode for the initial PID namespace.
    namespace = initial_namespace
    if sys.platform in {"linux", "android"}:  # pragma: linux cover
        # Kernels before Linux 3.8 lack this file, and sandboxes can hide it.
        with suppress(OSError):
            namespace = Path("/proc/self/ns/pid").stat().st_ino
    name = _escape_outside(_HOST_NAME_VERBATIM, socket.gethostname()) + (
        "" if namespace == initial_namespace else f"{NAMESPACE_MARK}{namespace:x}"
    )
    # A digest keeps distinct long hostnames distinct within the marker limit.
    host_name_limit: int = 253
    if len(name) > host_name_limit:
        digest_length = 8
        keep = host_name_limit - digest_length - 1
        name = f"{name[:keep]}-{hashlib.sha256(name[keep:].encode()).hexdigest()[:digest_length]}"
    # An escape is three characters and a kept byte is never '?', so a bare '?' can only mean an empty hostname.
    return name or "?"


def _escape_outside(verbatim: frozenset[int], name: str) -> str:
    return "".join(
        chr(byte) if byte in verbatim else f"?{byte:02x}" for byte in name.encode("utf-8", "surrogateescape")
    )


def describe_host_name(hostname: str) -> str:
    # Preserve existing ?xx escapes in hostnames written by filelock.
    return _escape_outside(_HOST_NAME_VERBATIM | {ord("?")}, hostname) or "?"


__all__ = [
    "NAMESPACE_MARK",
    "describe_host_name",
    "host_name",
]
