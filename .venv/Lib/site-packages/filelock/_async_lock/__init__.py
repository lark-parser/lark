"""Async lock lifecycle, task ownership and backend dispatch."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from importlib.machinery import ModuleSpec

__spec__ = cast("ModuleSpec", __spec__)

__lazy_modules__ = [
    f"{__spec__.parent}._backends",
    f"{__spec__.parent}._lock",
    f"{__spec__.parent}._owners",
    f"{__spec__.parent}._transitions",
]

from ._backends import (
    AsyncReadWriteBase,
    AsyncReadWriteProxy,
    AsyncSoftFileLease,
    AsyncSoftFileLock,
    AsyncStrictSoftFileLock,
    AsyncUnixFileLock,
    AsyncWindowsFileLock,
)
from ._lock import (
    AsyncAcquireReturnProxy,
    AsyncFileLockContext,
    AsyncFileLockMeta,
    AsyncThreadLocalFileContext,
    BaseAsyncFileLock,
)
from ._owners import TASKS_THREAD_ID, retire_task_holds_at_exit
from ._transitions import AsyncTransitionGate, AsyncTransitionUnavailableError

__all__ = [
    "TASKS_THREAD_ID",
    "AsyncAcquireReturnProxy",
    "AsyncFileLockContext",
    "AsyncFileLockMeta",
    "AsyncReadWriteBase",
    "AsyncReadWriteProxy",
    "AsyncSoftFileLease",
    "AsyncSoftFileLock",
    "AsyncStrictSoftFileLock",
    "AsyncThreadLocalFileContext",
    "AsyncTransitionGate",
    "AsyncTransitionUnavailableError",
    "AsyncUnixFileLock",
    "AsyncWindowsFileLock",
    "BaseAsyncFileLock",
    "retire_task_holds_at_exit",
]
