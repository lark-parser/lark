"""Host and process identities recorded in lock files."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    assert __spec__ is not None

__lazy_modules__ = [f"{__spec__.parent}._host", f"{__spec__.parent}._process"]

from ._host import describe_host_name, host_name
from ._process import link_host, owner_is_current_process, owner_is_stale, process_alive, process_start_token

__all__ = [
    "describe_host_name",
    "host_name",
    "link_host",
    "owner_is_current_process",
    "owner_is_stale",
    "process_alive",
    "process_start_token",
]
