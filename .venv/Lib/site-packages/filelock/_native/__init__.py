"""Operating-system file locks and descriptor operations."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from importlib.machinery import ModuleSpec

__spec__ = cast("ModuleSpec", __spec__)

__lazy_modules__ = [f"{__spec__.parent}._descriptor", f"{__spec__.parent}._unix", f"{__spec__.parent}._windows"]

from ._descriptor import lock_descriptor, unlock_descriptor
from ._unix import UnixFileLock, has_fcntl
from ._windows import WindowsFileLock

__all__ = [
    "UnixFileLock",
    "WindowsFileLock",
    "has_fcntl",
    "lock_descriptor",
    "unlock_descriptor",
]
