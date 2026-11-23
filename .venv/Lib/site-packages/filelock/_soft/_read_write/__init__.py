"""Cross-process and cross-host reader/writer lock over a generation log of immutable snapshots."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from importlib.machinery import ModuleSpec

    from ._async import AsyncAcquireSoftReadWriteReturnProxy, AsyncSoftReadWriteLock

__spec__ = cast("ModuleSpec", __spec__)

__lazy_modules__ = ["importlib", f"{__spec__.parent}._lock"]

from importlib import import_module

from ._lock import SoftReadWriteLock


def __getattr__(name: str) -> type[AsyncAcquireSoftReadWriteReturnProxy | AsyncSoftReadWriteLock]:
    # A sync lock can first release at shutdown, when importing the async executor is too late.
    if name in {"AsyncAcquireSoftReadWriteReturnProxy", "AsyncSoftReadWriteLock"}:
        return getattr(import_module("._async", __name__), name)
    raise AttributeError(name)


__all__ = [
    "AsyncAcquireSoftReadWriteReturnProxy",
    "AsyncSoftReadWriteLock",
    "SoftReadWriteLock",
]
