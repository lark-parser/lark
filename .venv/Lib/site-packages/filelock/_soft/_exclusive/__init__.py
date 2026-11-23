"""Exclusive soft locks backed by filesystem markers."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    assert __spec__ is not None

__lazy_modules__ = [f"{__spec__.parent}._lock", f"{__spec__.parent}._marker"]

from ._lock import SoftFileLock
from ._marker import MarkerSoftFileLock

__all__ = [
    "MarkerSoftFileLock",
    "SoftFileLock",
]
