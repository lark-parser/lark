"""Stale record detection and cleanup in the reader/writer log."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from importlib.machinery import ModuleSpec

__spec__ = cast("ModuleSpec", __spec__)

__lazy_modules__ = ["bisect", "hashlib", "pathlib", f"{__spec__.parent}._storage"]

import hashlib
from bisect import bisect_right
from pathlib import Path
from typing import TYPE_CHECKING

from ._storage import (
    GENERATIONS_DIRECTORY,
    HOLDERS_DIRECTORY,
    HOUSEKEEPING_BATCH,
    TEMPORARY_PREFIX,
    RecordFiles,
    holder_lease,
    is_token,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from ._generations import Snapshot


class Ledger:
    # Each observer measures record age on its own clock, so hosts need no shared time source.
    def __init__(self, clock: Callable[[], float]) -> None:
        self._clock = clock
        self._seen: dict[str, tuple[bytes | None, float]] = {}
        self._after: dict[str, str] = {}

    def observe(self, key: str, value: bytes | None, *, asked: float) -> float:
        # A pause after the read cannot count toward the age of the observed record.
        now = self._clock()
        digest = None if value is None else hashlib.sha256(value).digest()
        if (seen := self._seen.get(key)) is None or seen[0] != digest:
            self._seen[key] = (digest, now)
            return 0.0
        return asked - seen[1]

    def forget(self, key: str) -> None:
        self._seen.pop(key, None)

    def retain(self, keys: set[str]) -> None:
        self._seen = {key: seen for key, seen in self._seen.items() if key in keys}

    def next_batch(self, kind: str, names: list[str]) -> list[str]:
        # Keep a cursor across acquisitions so short holds can finish a sweep.
        start = bisect_right(names, self._after.get(kind, ""))
        if start == len(names):
            start = 0
        if batch := names[start : start + HOUSEKEEPING_BATCH]:
            self._after[kind] = batch[-1]
        return batch

    def retain_temporary(self, keys: set[str]) -> None:
        self._seen = {key: seen for key, seen in self._seen.items() if not key.startswith("temporary:") or key in keys}


class Sweep:
    def __init__(
        self, files: RecordFiles, root: str, stale_threshold: float, clock: Callable[[], float], ledger: Ledger
    ) -> None:
        self._files = files
        self._root = root
        self._stale_threshold = stale_threshold
        self._clock = clock
        self.ledger = ledger
        self._next_at = clock()

    def run(self, latest: Snapshot | None, token: str) -> None:
        # An overfull log can still be swept for abandoned temporary files even when its members are unknown.
        if (now := self._clock()) < self._next_at:
            return
        self._next_at = now + self._stale_threshold / 2
        watched = set() if latest is None else set(latest.members)
        if latest is not None:
            holders = Path(self._root, HOLDERS_DIRECTORY)
            unnamed = sorted(
                name
                for name in self._files.listdir(str(holders))
                if name != token and name not in latest.members and is_token(name)
            )
            self._sweep_batch(holders, unnamed, "holder", watched)
        generations = Path(self._root, GENERATIONS_DIRECTORY)
        temporary = sorted(name for name in self._files.listdir(str(generations)) if name.startswith(TEMPORARY_PREFIX))
        self._sweep_batch(generations, temporary, "temporary", watched)
        if latest is not None:
            self.ledger.retain(watched)
        else:
            self.ledger.retain_temporary(watched)

    def _sweep_batch(self, directory: Path, names: list[str], kind: str, watched: set[str]) -> None:
        watched.update(f"{kind}:{name}" for name in names)
        for name in self.ledger.next_batch(kind, names):
            key = f"{kind}:{name}"
            path = str(directory / name)
            if self.is_stale(key, path):
                self._files.unlink(path)
                self.ledger.forget(key)

    def is_stale(self, key: str, path: str) -> bool:
        asked = self._clock()
        record = self._files.read(path)
        return self.ledger.observe(key, record, asked=asked) >= max(self._stale_threshold, holder_lease(record) or 0.0)


__all__ = [
    "Ledger",
    "Sweep",
]
