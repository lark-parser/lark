"""Lock cleanup during garbage collection and interpreter shutdown."""

from __future__ import annotations

__lazy_modules__ = ["types"]

import atexit
import os
import sys
import types
from dataclasses import dataclass
from functools import cache, partial
from threading import active_count, local
from typing import TYPE_CHECKING, Final
from weakref import WeakValueDictionary, ref

if TYPE_CHECKING:
    from ._lock import BaseFileLock


@cache
def resolve_lazy_imports_before_shutdown() -> None:
    if hasattr(types, "LazyImportType"):  # pragma: >=3.15 cover
        atexit.register(_resolve_lazy_imports)


def _resolve_lazy_imports() -> None:  # pragma: >=3.15 cover
    for name, module in list(sys.modules.items()):
        if name == "filelock" or name.startswith("filelock."):
            for attribute, value in list(module.__dict__.items()):
                if type(value) is types.LazyImportType:
                    getattr(module, attribute)


def interpreter_exiting() -> bool:
    return _EXIT_RELEASE.running or sys.is_finalizing()


def defer_singleton_release(lock: BaseFileLock) -> None:
    # A strong reference from the callback would keep the singleton alive through its state.
    holder = FinalizerState(state=lock.__dict__)
    lock._finalizer_state = holder  # ruff:ignore[private-member-access]  # survives until the weakref callback
    _UNREACHABLE_LOCKS.add(ref(lock, partial(_finalize_unreachable, ref(holder), type(lock))))


@dataclass(  # simplint: ignore[dataclass-frozen]  # state is reset to None on finalize
    slots=True, weakref_slot=True, kw_only=True
)
class FinalizerState:
    state: (
        dict[str, object] | None  # simplint: ignore[imprecise-annotation]  # the instance __dict__ holds any value
    )


def _finalize_unreachable(holder: ref[FinalizerState], cls: type[BaseFileLock], reference: ref[BaseFileLock]) -> None:
    _UNREACHABLE_LOCKS.discard(reference)
    if (finalizer_state := holder()) is None or (state := finalizer_state.state) is None:
        return  # pragma: no cover  # only a collector freeing a resurrected lock as part of a cycle drops the holder
    finalizer_state.state = None
    # Dropping this uncached instance runs the original finalizer with its original state.
    stand_in = object.__new__(cls)
    stand_in.__dict__ = state
    del stand_in


# Keep the callback alive until the singleton cache drops its entry.
_UNREACHABLE_LOCKS: Final[set[ref[BaseFileLock]]] = set()


#: Identity keys also track unhashable lock subclasses at shutdown.
LIVE_LOCKS: Final[WeakValueDictionary[int, BaseFileLock]] = WeakValueDictionary()


class _ExitRelease(local):
    # Per thread, so a daemon thread still running at exit, and a child it forks, keep their fork bookkeeping.
    running = False


#: Marks the thread releasing live locks at exit, where no other thread's event loop runs a scheduled release.
_EXIT_RELEASE: Final[_ExitRelease] = _ExitRelease()


def _release_live_locks() -> None:
    # Finalizers run too late if module teardown has already started.
    pid = os.getpid()
    # A running daemon may still own a shared lock at exit.
    sole_thread = active_count() == 1
    _EXIT_RELEASE.running = True
    try:
        for lock in [
            lock
            for lock in LIVE_LOCKS.values()
            if lock._creator_pid == pid  # ruff:ignore[private-member-access]  # the module owns the locks it tracks
            and (sole_thread or lock.is_thread_local())
        ]:
            lock._release_abandoned_holds(exited_only=True)  # ruff:ignore[private-member-access]  # ditto
    finally:
        # A later exit handler may still fork, and its child is not exiting.
        _EXIT_RELEASE.running = False


atexit.register(_release_live_locks)


__all__ = [
    "LIVE_LOCKS",
    "FinalizerState",
    "defer_singleton_release",
    "interpreter_exiting",
    "resolve_lazy_imports_before_shutdown",
]
