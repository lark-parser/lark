"""SQLite reader and writer locks."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    assert __spec__ is not None

__lazy_modules__ = ["importlib", f"{__spec__.parent}._lock"]

from importlib import import_module
from typing import TYPE_CHECKING

from ._lock import ReadWriteLock

if TYPE_CHECKING:
    from ._async import AsyncAcquireReadWriteReturnProxy, AsyncReadWriteLock


def __getattr__(name: str) -> type[AsyncAcquireReadWriteReturnProxy | AsyncReadWriteLock]:
    if name in {"AsyncAcquireReadWriteReturnProxy", "AsyncReadWriteLock"}:
        return getattr(import_module("._async", __name__), name)
    raise AttributeError(name)


__all__ = [
    "AsyncAcquireReadWriteReturnProxy",
    "AsyncReadWriteLock",
    "ReadWriteLock",
]
