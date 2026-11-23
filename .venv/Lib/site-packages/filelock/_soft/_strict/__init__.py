"""Strict soft locks and their on-disk claim protocol."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from importlib.machinery import ModuleSpec

__spec__ = cast("ModuleSpec", __spec__)

__lazy_modules__ = [
    f"{__spec__.parent}._claims",
    f"{__spec__.parent}._directories",
    f"{__spec__.parent}._lock",
    f"{__spec__.parent}._publication",
    f"{__spec__.parent}._release",
]

from ._claims import StrictSoftFileClaim, StrictSoftFileClaimState
from ._directories import pin_directories
from ._lock import StrictSoftFileLock
from ._publication import link_no_follow, raise_if_hard_links_unsupported
from ._release import StrictRelease

__all__ = [
    "StrictRelease",
    "StrictSoftFileClaim",
    "StrictSoftFileClaimState",
    "StrictSoftFileLock",
    "link_no_follow",
    "pin_directories",
    "raise_if_hard_links_unsupported",
]
