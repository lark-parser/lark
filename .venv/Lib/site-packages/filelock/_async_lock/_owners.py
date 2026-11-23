"""Lock holds owned by individual asyncio tasks."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from importlib.machinery import ModuleSpec

__spec__ = cast("ModuleSpec", __spec__)

__lazy_modules__ = ["asyncio", "concurrent.futures", "filelock._core", f"{__spec__.parent}._executor"]

import asyncio
import time
from concurrent.futures import Future as ConcurrentFuture
from dataclasses import dataclass
from threading import Lock
from typing import TYPE_CHECKING, Final, Literal
from weakref import WeakKeyDictionary

from filelock._core import Timeout, fork_transition, resolve_read_write_timeout

from ._executor import BackendOutcome, drain_cancellation, wait_until_done

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Hashable

    from filelock._core import ReadWriteBackend


#: The holder an async wrapper records its backend level under. No thread has this identifier, so sync code on the
#: executor thread that took the level cannot re-enter or release it.
TASKS_THREAD_ID: Final[int] = 0


_TASK_OWNERS: Final[WeakKeyDictionary[ReadWriteBackend, _TaskOwners]] = WeakKeyDictionary()


_TASK_OWNERS_LOCK: Final[Lock] = Lock()


def retire_task_holds_at_exit(backend: ReadWriteBackend) -> bool:  # pragma: needs hard-link
    # A published task level already has a table. Shutdown must not wait on fork admission to look it up.
    return _TASK_OWNERS[backend].retire_stopped_loops()


def task_owners_for(sync_lock: ReadWriteBackend) -> _TaskOwners:
    # Singleton wrappers share one sync lock, so they must share its task holds too.
    with fork_transition(), _TASK_OWNERS_LOCK:
        if (owners := _TASK_OWNERS.get(sync_lock)) is None:
            owners = _TASK_OWNERS[sync_lock] = _TaskOwners()
        return owners


class _TaskOwners:
    # Executor thread IDs cannot distinguish tasks, and singleton wrappers can span event loops.
    def __init__(self) -> None:
        self._lock: Final[Lock] = Lock()
        self._mode: Literal["read", "write"] | None = None
        self._holds: dict[
            asyncio.Task[object], _TaskHold  # simplint: ignore[imprecise-annotation]  # task results vary
        ] = {}
        self._transitioning = False
        self._entering_via: Hashable | None = None
        self._read_waiters: dict[ConcurrentFuture[None], Hashable] = {}
        self._write_queue: dict[
            asyncio.Task[object],  # simplint: ignore[imprecise-annotation]  # task results vary
            tuple[ConcurrentFuture[None], Hashable],
        ] = {}
        self._transition_waiters: set[ConcurrentFuture[None]] = set()

    async def acquire(  # ruff:ignore[too-many-arguments]  # one keyword per piece of wrapper state the table consults
        self,
        mode: Literal["read", "write"],
        *,
        timeout: float,
        blocking: bool,
        lock_file: str,
        via: Hashable,
        enter: Callable[[float], Awaitable[None]],
        joinable: Callable[[], bool],
        raise_if_unusable: Callable[[], None],
        check_after_enter: Callable[[], Awaitable[None]],
    ) -> None:
        task = _current_task()
        timeout = resolve_read_write_timeout(timeout, blocking=blocking)
        deadline = None if not blocking or timeout < 0 else time.perf_counter() + timeout
        try:
            while isinstance(
                admission := self._admit(
                    task,
                    mode,
                    lock_file,
                    via=via,
                    joinable=joinable,
                    raise_if_unusable=raise_if_unusable,
                ),
                ConcurrentFuture,
            ):
                try:
                    if not blocking or (deadline is not None and time.perf_counter() >= deadline):
                        raise Timeout(lock_file)
                    wait = None if deadline is None else deadline - time.perf_counter()
                    await asyncio.wait((asyncio.wrap_future(admission),), timeout=wait)
                finally:
                    self._forget(admission)
        finally:
            if mode == "write":
                with self._lock:
                    self._write_queue.pop(task, None)
                    self._notify()
        if admission == "held":
            return
        try:
            await enter(-1 if deadline is None else max(0.0, deadline - time.perf_counter()))
        except BaseException:
            self._finish_transition(mode=None)
            raise
        self._finish_transition(mode=mode, holds={task: _TaskHold(depths={via: 1})})
        await check_after_enter()

    def _admit(  # ruff:ignore[too-many-arguments]  # the acquire's state, passed through under the table lock
        self,
        task: asyncio.Task[object],  # simplint: ignore[imprecise-annotation]  # task results vary
        mode: Literal["read", "write"],
        lock_file: str,
        *,
        via: Hashable,
        joinable: Callable[[], bool],
        raise_if_unusable: Callable[[], None],
    ) -> Literal["held", "enter"] | ConcurrentFuture[None]:
        with self._lock:
            raise_if_unusable()
            # Sync code may have released the level this table recorded.
            if self._mode is not None and not self._transitioning and not joinable():
                self._holds.clear()
                self._mode = None
                self._notify()
            if (hold := self._holds.get(task)) is not None:
                if self._mode != mode:
                    msg = (
                        f"Cannot acquire {mode} lock on {lock_file}: already holding a "
                        f"{'write' if mode == 'read' else 'read'} lock "
                        f"({'downgrade' if mode == 'read' else 'upgrade'} not allowed)"
                    )
                    raise RuntimeError(msg)
                hold.depths[via] = hold.depths.get(via, 0) + 1
                return "held"
            if not self._transitioning:
                if mode == "read" and self._mode == "read" and not self._write_queue:
                    self._holds[task] = _TaskHold(depths={via: 1})
                    return "held"
                if not self._holds and next(iter(self._write_queue), task) is task:
                    self._transitioning, self._mode, self._entering_via = True, mode, via
                    return "enter"
            ticket: ConcurrentFuture[None] = ConcurrentFuture()
            if mode == "write":
                self._write_queue[task] = ticket, via
            else:
                self._read_waiters[ticket] = via
            return ticket

    def _forget(self, ticket: ConcurrentFuture[None]) -> None:
        with self._lock:
            self._read_waiters.pop(ticket, None)
            self._transition_waiters.discard(ticket)

    def _notify(self) -> None:
        if self._transitioning:
            return
        for ticket in self._transition_waiters:
            ticket.set_result(None)
        self._transition_waiters.clear()
        if self._write_queue:
            ticket, _ = next(iter(self._write_queue.values()))
            if not self._holds and not ticket.done():
                ticket.set_result(None)
        elif self._mode != "write":
            for ticket in self._read_waiters:
                ticket.set_result(None)
            self._read_waiters.clear()

    def _finish_transition(
        self,
        *,
        mode: Literal["read", "write"] | None,
        holds: dict[asyncio.Task[object], _TaskHold]  # simplint: ignore[imprecise-annotation]  # task results vary
        | None = None,
    ) -> None:
        with self._lock:
            self._transitioning, self._mode, self._entering_via = False, mode, None
            if mode is not None and holds:
                for task, hold in holds.items():
                    self._holds.setdefault(task, _TaskHold(depths={})).depths.update(hold.depths)
            self._notify()

    def wake_via(self, via: Hashable) -> None:
        with self._lock:
            for ticket, waiting_via in tuple(self._read_waiters.items()):
                if waiting_via is via:
                    del self._read_waiters[ticket]
                    ticket.set_result(None)
            for ticket, waiting_via in self._write_queue.values():
                if waiting_via is via and not ticket.done():
                    ticket.set_result(None)

    async def release(
        self,
        *,
        force: bool,
        lock_file: str,
        via: Hashable,
        leave: Callable[[], asyncio.Future[BackendOutcome[None]]],
        still_held: Callable[[], bool],
    ) -> None:
        task = _current_task()
        with self._lock:
            if (hold := self._holds.get(task)) is None or via not in hold.depths:
                if force:
                    return
                msg = f"Cannot release a lock on {lock_file} that is not held by this task through this wrapper"
                raise RuntimeError(msg)
            if not force and hold.depths[via] > 1:
                hold.depths[via] -= 1
                return
            removed = hold.depths.pop(via)
            if hold.depths:
                return
            del self._holds[task]
            if self._holds:
                return
            self._transitioning = True
            mode = self._mode
        if not still_held():
            self._finish_transition(mode=None)
            msg = f"Cannot release a lock on {lock_file} that is not held by this task"
            raise RuntimeError(msg)
        try:
            cancellation = await drain_cancellation(leave())
        except BaseException:
            hold.depths[via] = removed
            # A failed release can be retried only while the backend holds its level.
            self._finish_transition(mode=mode if still_held() else None, holds={task: hold})
            raise
        self._finish_transition(mode=None)
        if cancellation is not None:
            # The release succeeded, so a restored hold would be a phantom no backend call can clear.
            raise cancellation

    async def retire(
        self,
        via: Hashable | None,
        *,
        leave: Callable[[], asyncio.Future[BackendOutcome[None]]],
        still_held: Callable[[], bool],
    ) -> None:
        # Other tasks must wait while the last wrapper releases the shared backend hold.
        cancellation: asyncio.CancelledError | None = None
        while isinstance(settled := self._drop_holds_via(via), ConcurrentFuture):
            try:
                await wait_until_done(asyncio.wrap_future(settled))
            except asyncio.CancelledError as error:
                cancellation = error
            finally:
                self._forget(settled)
        mode, dropped = settled
        if via is None or (mode is not None and still_held()):
            try:
                cancellation = await drain_cancellation(leave()) or cancellation
            except BaseException:
                # A close that failed with the backend still holding stays retryable, as a failed release does.
                self._finish_transition(mode=mode if still_held() else None, holds=dropped)
                raise
            self._finish_transition(mode=None)
        elif mode is not None:
            # Sync code already ended the level taken for tasks, so there is nothing to give back.
            self._finish_transition(mode=None)
        if cancellation is not None:
            raise cancellation

    def _drop_holds_via(
        self, via: Hashable | None
    ) -> (
        tuple[
            Literal["read", "write"] | None,
            dict[asyncio.Task[object], _TaskHold],  # simplint: ignore[imprecise-annotation]  # task results vary
        ]
        | ConcurrentFuture[None]
    ):
        with self._lock:
            if self._transitioning:
                # Closing this wrapper need not wait for an unrelated acquire.
                if via is not None and self._entering_via is not None and self._entering_via is not via:
                    return None, {}
                ticket: ConcurrentFuture[None] = ConcurrentFuture()
                self._transition_waiters.add(ticket)
                return ticket
            if via is None:
                dropped = dict(self._holds)
                self._holds.clear()
            else:
                dropped = {}
                for task, hold in list(self._holds.items()):
                    if (count := hold.depths.pop(via, None)) is not None:
                        dropped[task] = _TaskHold(depths={via: count})
                        if not hold.depths:
                            del self._holds[task]
            if self._holds and via is not None:
                return None, dropped
            mode = self._mode
            self._transitioning = mode is not None or via is None
            return mode, dropped

    def retire_stopped_loops(self) -> bool:  # pragma: needs hard-link
        # Admission checks the backend under this lock. Exit cleanup already holds the backend lock.
        if not self._lock.acquire(blocking=False):
            return False
        try:
            if self._transitioning or any(task.get_loop().is_running() for task in self._holds):
                return False
            # A new reader must take its own backend level once exit cleanup has claimed the old one.
            self._mode = None
            self._holds.clear()
            self._notify()
            return True
        finally:
            self._lock.release()


def _current_task() -> asyncio.Task[object]:  # simplint: ignore[imprecise-annotation]  # task results vary
    if (task := asyncio.current_task()) is None:
        msg = "an async reader/writer lock must be used from inside an asyncio task"
        raise RuntimeError(msg)
    return task


@dataclass(frozen=True, slots=True, kw_only=True)
class _TaskHold:
    depths: dict[Hashable, int]


__all__ = [
    "TASKS_THREAD_ID",
    "retire_task_holds_at_exit",
    "task_owners_for",
]
