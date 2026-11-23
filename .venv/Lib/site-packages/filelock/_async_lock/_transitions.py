"""Queue for serializing acquisition and release across event loops."""

from __future__ import annotations

__lazy_modules__ = ["asyncio", "collections", "concurrent.futures", "threading"]

import asyncio
import contextlib
import time
from collections import deque
from concurrent.futures import Future as ConcurrentFuture
from threading import Lock
from typing import TYPE_CHECKING, Final, cast

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable


class AsyncTransitionGate:
    """Give one task at a time access to a lock transition, in arrival order."""

    def __init__(self) -> None:
        self._queue_lock: Final[Lock] = Lock()
        self._queue: Final[deque[ConcurrentFuture[None]]] = deque()

    @contextlib.asynccontextmanager
    async def hold(self, *, owed: Callable[[], bool] | None = None) -> AsyncGenerator[asyncio.CancelledError | None]:
        """
        Wait for a turn to complete a transition.

        :param owed: keep a canceled task queued while it still owes a release
        :yields: the deferred cancellation, or None if the wait was uninterrupted
        :raises asyncio.CancelledError: the caller was canceled without an outstanding release
        """
        ticket: ConcurrentFuture[None] = ConcurrentFuture()
        cancellation: asyncio.CancelledError | None = None

        def given_up() -> bool:
            return owed is None or not owed()

        try:
            self._join(ticket)
            while not ticket.done():
                try:
                    await self._wait_for_turn(
                        ticket,
                        blocking=True,
                        cancel_check=None if cancellation is None else given_up,
                        deadline=None,
                        poll_interval=0.05,
                    )
                except asyncio.CancelledError as error:
                    if given_up():
                        raise
                    cancellation = error
                except AsyncTransitionUnavailableError:
                    raise cast("asyncio.CancelledError", cancellation) from None
            yield cancellation
        finally:
            self._leave(ticket)

    def _join(self, ticket: ConcurrentFuture[None]) -> None:
        with self._queue_lock:
            self._queue.append(ticket)
            if len(self._queue) == 1:
                ticket.set_result(None)

    async def _wait_for_turn(
        self,
        ticket: ConcurrentFuture[None],
        *,
        blocking: bool,
        cancel_check: Callable[[], bool] | None,
        deadline: float | None,
        poll_interval: float,
    ) -> None:
        if not blocking:
            raise AsyncTransitionUnavailableError
        waiter = asyncio.wrap_future(ticket)
        while not ticket.done():
            if cancel_check is not None and cancel_check():
                raise AsyncTransitionUnavailableError
            wait_interval = poll_interval
            if deadline is not None:
                if (remaining := deadline - time.perf_counter()) <= 0:
                    raise AsyncTransitionUnavailableError
                wait_interval = min(wait_interval, remaining)
            await asyncio.wait((waiter,), timeout=wait_interval)
            # A hand-off that a signal handler's exception cut short leaves the head undone, so the head settles itself.
            self._settle_head()

    def _settle_head(self) -> None:
        with self._queue_lock:
            self._settle_head_locked()

    def _settle_head_locked(self) -> None:
        if self._queue and not (head := self._queue[0]).done():
            head.set_result(None)

    def _leave(self, ticket: ConcurrentFuture[None]) -> None:
        with self._queue_lock:
            try:
                self._queue.remove(ticket)
            except ValueError:
                # The join never completed, or this ticket already left.
                return
            self._settle_head_locked()

    @contextlib.asynccontextmanager
    async def hold_for_acquire(
        self,
        *,
        blocking: bool,
        cancel_check: Callable[[], bool] | None,
        deadline: float | None,
        poll_interval: float,
    ) -> AsyncGenerator[None]:
        """
        Wait for a turn to attempt acquisition.

        :param blocking: whether to queue behind another transition
        :param cancel_check: optional callback that cancels a queued wait when it returns true
        :param deadline: absolute :func:`time.perf_counter` deadline, or None for no limit
        :param poll_interval: seconds between cancellation and deadline checks
        :yields: None while the caller owns the turn
        :raises AsyncTransitionUnavailableError: a queued wait was refused, canceled or timed out
        """
        ticket: ConcurrentFuture[None] = ConcurrentFuture()
        try:
            self._join(ticket)
            if not ticket.done():
                await self._wait_for_turn(
                    ticket,
                    blocking=blocking,
                    cancel_check=cancel_check,
                    deadline=deadline,
                    poll_interval=poll_interval,
                )
            yield
        finally:
            self._leave(ticket)


class AsyncTransitionUnavailableError(Exception):
    """A queued task could not enter an acquisition transition."""


__all__ = [
    "AsyncTransitionGate",
    "AsyncTransitionUnavailableError",
]
