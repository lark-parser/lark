"""Heartbeat timing and renewal for reader/writer leases."""

from __future__ import annotations

__lazy_modules__ = ["math"]

import sys
import threading
import time
from math import isfinite
from typing import TYPE_CHECKING, Final, NamedTuple

from filelock._core import check_timeout_max, override, seconds

if TYPE_CHECKING:
    from collections.abc import Callable


class HeartbeatThread(threading.Thread):
    def __init__(
        self,
        refresh: Callable[[], bool],
        interval: float,
        stop_event: threading.Event,
        name: str,
    ) -> None:
        super().__init__(name=name, daemon=True)
        self._refresh = refresh
        self._interval = interval
        self._stop_event = stop_event

    @override
    def run(self) -> None:
        # Waiters must observe thread exit even if a callback raises.
        try:
            while not self._stop_event.wait(self._interval):
                if not self._refresh():
                    return
        finally:
            self._stop_event.set()


_LEASE_CLOCK_ID: Final[int | None] = getattr(
    time, "CLOCK_MONOTONIC" if sys.platform == "darwin" else "CLOCK_BOOTTIME", None
)


def lease_clock() -> float:
    # A peer can judge a record stale while this host sleeps, so renewal must count that elapsed time.
    read_clock = getattr(time, "clock_gettime", None)
    if _LEASE_CLOCK_ID is not None and read_clock is not None:  # pragma: needs suspend-clock
        return read_clock(_LEASE_CLOCK_ID)
    return time.monotonic()  # pragma: lacks suspend-clock


def validate_intervals(heartbeat_interval: float, stale_threshold: float | None, poll_interval: float) -> _Intervals:
    heartbeat_interval = seconds("heartbeat_interval", heartbeat_interval)
    if not isfinite(heartbeat_interval) or heartbeat_interval <= 0:
        msg = f"heartbeat_interval must be positive and finite, got {heartbeat_interval}"
        raise ValueError(msg)
    # The heartbeat thread waits this long between refreshes, and Event.wait overflows past TIMEOUT_MAX.
    check_timeout_max("heartbeat_interval", heartbeat_interval)
    stale_threshold = heartbeat_interval * 3 if stale_threshold is None else seconds("stale_threshold", stale_threshold)
    if not isfinite(stale_threshold) or stale_threshold <= heartbeat_interval:
        msg = (
            f"stale_threshold must exceed heartbeat_interval ({heartbeat_interval}) "
            f"and be finite, got {stale_threshold}"
        )
        raise ValueError(msg)
    if not isfinite(poll_interval := seconds("poll_interval", poll_interval)) or poll_interval <= 0:
        msg = f"poll_interval must be positive and finite, got {poll_interval}"
        raise ValueError(msg)
    check_timeout_max("poll_interval", poll_interval)
    # A waiting writer refreshes its record once per poll, so a poll slower than the threshold reads as dead.
    if poll_interval >= stale_threshold:
        msg = f"poll_interval must be below stale_threshold ({stale_threshold}), got {poll_interval}"
        raise ValueError(msg)
    return _Intervals(heartbeat_interval, stale_threshold, poll_interval)


class _Intervals(NamedTuple):
    heartbeat_interval: float
    stale_threshold: float
    poll_interval: float


__all__ = [
    "HeartbeatThread",
    "lease_clock",
    "validate_intervals",
]
