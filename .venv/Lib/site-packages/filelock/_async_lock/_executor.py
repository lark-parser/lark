"""Worker submission and cancellation handling for async locks."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from importlib.machinery import ModuleSpec

__spec__ = cast("ModuleSpec", __spec__)

__lazy_modules__ = ["asyncio", "concurrent.futures", "contextlib", "filelock._core", f"{__spec__.parent}._transitions"]

import asyncio
import contextlib
from concurrent.futures import Future as ConcurrentFuture
from dataclasses import dataclass
from typing import TYPE_CHECKING, Generic, NoReturn, TypeVar, cast

from filelock._core import append_exception_context, raise_chained_errors

from ._transitions import AsyncTransitionGate

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from concurrent.futures import Executor, ThreadPoolExecutor
_T = TypeVar("_T")


class AsyncClose:
    def __init__(self) -> None:
        self._gate = AsyncTransitionGate()
        self._join: tuple[ThreadPoolExecutor, ConcurrentFuture[None]] | None = None

    async def close(self, retire: Callable[[], Awaitable[None]], executor: Executor | None) -> None:
        async with self._gate.hold():
            await retire()
            if executor is None:
                return
            if self._join is None:
                pool = cast("ThreadPoolExecutor", executor)
                pool.shutdown(wait=False)
                if not pool._threads:  # ruff:ignore[private-member-access]  # only the pool tracks its workers
                    return
                # A queued job may still need the event loop after its default executor shuts down.
                joiner = type(pool)(max_workers=1)
                try:
                    self._join = joiner, joiner.submit(pool.shutdown)
                finally:
                    joiner.shutdown(wait=False)
            joiner, joined = self._join
        await asyncio.shield(asyncio.wrap_future(joined))
        joiner.shutdown()


async def drain_cancellation(future: asyncio.Future[BackendOutcome[None]]) -> asyncio.CancelledError | None:
    # Returning cancellation lets the caller commit a successful backend operation first.
    try:
        await wait_until_done(future)
    except asyncio.CancelledError as cancellation:
        try:
            await drain_future(future)
        except BaseException as error:  # ruff:ignore[blind-except]  # reported with the cancellation below
            raise_cancelled_error(cancellation, error)
        return cancellation
    future_result(future)
    return None


async def wait_until_done(future: asyncio.Future[_T]) -> None:
    if not future.done():
        await asyncio.wait((future,))


async def drain_future(future: asyncio.Future[BackendOutcome[_T]]) -> _T:
    while not future.done():
        with contextlib.suppress(asyncio.CancelledError):
            await wait_until_done(future)
    return future_result(future)


def raise_cancelled_error(cancellation: asyncio.CancelledError, error: BaseException) -> NoReturn:
    # Keep the backend failure and its cancellation in the same exception chain.
    if (context := error.__context__) is not None and context is not cancellation:
        if (cancellation_context := cancellation.__context__) is not None:
            append_exception_context(context, cancellation_context)
        cancellation.__context__ = context
    error.__context__ = cancellation
    raise_chained_errors(error)


def future_result(future: asyncio.Future[BackendOutcome[_T]]) -> _T:
    outcome = future.result()
    if (error := outcome.error) is None:
        return cast("_T", outcome.value)
    context = error.__context__
    try:
        raise error  # ruff:ignore[raise-within-try]  # the handler restores context changed across the async boundary
    except BaseException:
        error.__context__ = context
        raise


def run_in_executor(
    loop: asyncio.AbstractEventLoop, executor: Executor | None, func: Callable[[], _T]
) -> asyncio.Future[BackendOutcome[_T]]:
    outcome: asyncio.Future[BackendOutcome[_T]] = loop.create_future()

    def settle(call: asyncio.Future[BackendOutcome[_T]]) -> None:
        try:
            result = call.result()
        except asyncio.CancelledError:
            # Executor shutdown canceled the job before it ran. The caller still owns its task.
            result = BackendOutcome(error=RuntimeError("the executor shut down before running the lock backend call"))
        outcome.set_result(result)

    submit_call(loop, executor, func).add_done_callback(settle)
    return outcome


@dataclass(frozen=True, slots=True, kw_only=True)
class BackendOutcome(Generic[_T]):
    value: _T | None = None
    error: BaseException | None = None


def submit_call(
    loop: asyncio.AbstractEventLoop, executor: Executor | None, func: Callable[[], _T]
) -> asyncio.Future[BackendOutcome[_T]]:
    # ThreadPoolExecutor can leave a call queued when starting a worker raises; do not run it after submission fails.
    call: ConcurrentFuture[BackendOutcome[_T]] = ConcurrentFuture()

    def run() -> BackendOutcome[_T]:
        if not call.set_running_or_notify_cancel():
            return BackendOutcome()
        result = capture_call(func)
        call.set_result(result)
        return result

    try:
        return loop.run_in_executor(executor, run)
    except BaseException:
        if call.cancel():
            raise
        # The worker started before submission raised, so its result must settle the backend state.
        return asyncio.wrap_future(call, loop=loop)


def capture_call(func: Callable[[], _T]) -> BackendOutcome[_T]:
    try:
        return BackendOutcome(value=func())
    except BaseException as error:  # ruff:ignore[blind-except]  # backend control-flow exceptions are operation results
        return BackendOutcome(error=error)


async def capture_awaitable(awaitable: Awaitable[_T]) -> BackendOutcome[_T]:
    try:
        return BackendOutcome(value=await awaitable)
    except BaseException as error:  # ruff:ignore[blind-except]  # backend cancellation must remain distinct from caller cancellation
        return BackendOutcome(error=error)


__all__ = [
    "AsyncClose",
    "BackendOutcome",
    "capture_awaitable",
    "capture_call",
    "drain_cancellation",
    "drain_future",
    "future_result",
    "raise_cancelled_error",
    "run_in_executor",
    "submit_call",
    "wait_until_done",
]
