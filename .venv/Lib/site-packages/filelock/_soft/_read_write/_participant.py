"""Reader and writer participation in the generation log."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from importlib.machinery import ModuleSpec

__spec__ = cast("ModuleSpec", __spec__)

__lazy_modules__ = [
    "contextlib",
    "filelock",
    "pathlib",
    f"{__spec__.parent}._generations",
    f"{__spec__.parent}._storage",
    f"{__spec__.parent}._sweep",
]

from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from time import sleep
from typing import TYPE_CHECKING, Final, Literal

from filelock import SoftFileLockProtocolError

from ._generations import GenerationListingOverflowError, GenerationLog, Snapshot
from ._storage import HOLDERS_DIRECTORY, RecordFiles, TreeReplacedError, encode_holder, holder_header, new_token
from ._sweep import Ledger, Sweep

if TYPE_CHECKING:
    from collections.abc import Callable

Mode = Literal["read", "write"]
HeartbeatOutcome = Literal["ok", "lost", "transient"]


class Participant:
    def __init__(  # ruff:ignore[too-many-arguments]  # the lock binds shared storage once per instance
        self,
        files: RecordFiles,
        root: str,
        mode: Mode,
        *,
        stale_threshold: float,
        clock: Callable[[], float],
        lease_clock: Callable[[], float],
        ledger: Ledger,
        log: GenerationLog,
    ) -> None:
        self.token = new_token()
        self.mode: Final[Mode] = mode
        self.generation: int | None = None
        self._files = files
        self._root = root
        self._stale_threshold = stale_threshold
        self._clock = clock
        self._lease_clock = lease_clock
        self._log = log
        self._holder: _HolderRecord | None = None
        self._entered = False
        self._cleanup = Sweep(files, root, stale_threshold, clock, ledger)

    def publish(self) -> None:
        # The record must be visible before the token enters a snapshot.
        self._files.prepare(self._root)
        self._create_holder()

    def _create_holder(self) -> None:
        asked = self._lease_clock()
        try:
            identity = self._files.create(self._holder_path(self.token), self._record())
        except FileNotFoundError:
            self._files.prepare(self._root, force=True)
            identity = self._files.create(self._holder_path(self.token), self._record())
        self._holder = _HolderRecord(identity=identity, refreshed=asked)

    def _holder_path(self, token: str) -> str:
        return str(Path(self._root, HOLDERS_DIRECTORY, token))

    def _record(self) -> bytes:
        return encode_holder(self.token, new_token(), self._stale_threshold)

    def advance(self) -> bool:
        # A lost publication race can succeed on a fresh snapshot before the next poll.
        for _ in range(4):
            if (outcome := self._attempt()) is not None:
                return outcome
        return False

    def _attempt(self) -> bool | None:
        try:
            latest = self._log.latest()
        except GenerationListingOverflowError:
            self._cleanup.run(None, self.token)
            raise
        if not self._keep_claim_fresh(latest):
            return None
        self._cleanup.run(latest, self.token)
        stale = frozenset(
            token for token in latest.members - {self.token} if self._cleanup.is_stale(token, self._holder_path(token))
        )
        writer = None if latest.writer in stale else latest.writer
        readers = latest.readers - stale
        if not self._entered:
            if writer is not None:
                # An eviction can still proceed while the writer blocks admission.
                if stale:
                    self._commit(latest, writer, readers, stale)
                return False
            writer, readers = (self.token, readers) if self.mode == "write" else (None, readers | {self.token})
        granted = self.mode == "read" or not readers
        if self._entered and not stale and not granted:
            return False
        if (generation := self._commit(latest, writer, readers, stale)) is None:
            return None
        if self._outlived_its_lease(self._holder):
            self._start_over()
            return None
        self._entered = True
        if granted:
            self.generation = generation
        return granted

    def _keep_claim_fresh(self, latest: Snapshot) -> bool:
        # An NFS retry can report a committed link as lost. A peer can also evict a waiting writer.
        holder = self._holder
        kept = self._refresh_nonce()
        if self._outlived_its_lease(holder):
            self._start_over()
            return False
        if not kept:
            with suppress(FileExistsError):
                self._create_holder()
        self._entered = self.token in latest.members
        return True

    def _refresh_nonce(self) -> bool:
        if (holder := self._holder) is None:
            return False
        asked = self._lease_clock()
        if kept := self._files.overwrite(
            self._holder_path(self.token), self._record(), holder.identity, holder_header(self.token)
        ):
            self._holder = _HolderRecord(identity=holder.identity, refreshed=asked)
        return kept

    def _commit(
        self, latest: Snapshot, writer: str | None, readers: frozenset[str], stale: frozenset[str]
    ) -> int | None:
        successor = Snapshot(generation=latest.generation + 1, writer=writer, readers=readers)
        if not self._log.commit(successor):
            return None
        for token in stale:
            self._files.unlink(self._holder_path(token))
            self._cleanup.ledger.forget(token)
        return successor.generation

    def _outlived_its_lease(self, holder: _HolderRecord | None) -> bool:
        return holder is not None and self._lease_clock() - holder.refreshed >= self._stale_threshold

    def _start_over(self) -> None:
        # A late sweep can still remove the old name after its nonce changes.
        self.leave()
        self.token = new_token()
        self._create_holder()

    def leave(self) -> None:
        # Once the lease expires, further retries cannot preserve the hold.
        give_up = self._clock() + self._stale_threshold
        delay = 0.001
        with suppress(TreeReplacedError):
            try:
                while self.token in (latest := self._log.latest()).members:
                    successor = Snapshot(
                        generation=latest.generation + 1,
                        writer=None if latest.writer == self.token else latest.writer,
                        readers=latest.readers - {self.token},
                    )
                    if self._log.commit(successor):
                        break
                    if (remaining := give_up - self._clock()) <= 0:
                        msg = "could not withdraw holder from generation log before its stale threshold"
                        raise SoftFileLockProtocolError(self._log.lock_file, None, msg)
                    sleep(min(delay, remaining))
                    delay = min(delay * 2, 0.01)
            finally:
                self._entered = False
                self.generation = None
                self._files.unlink(self._holder_path(self.token))

    def heartbeat(self) -> tuple[HeartbeatOutcome, OSError | None]:
        # Only a failed nonce refresh counts against liveness. A failed scan says nothing about this holder.
        try:
            if not self._refresh_nonce():
                return "lost", None
        except TreeReplacedError:
            return "lost", None
        except OSError as error:
            return "transient", error
        try:
            try:
                latest = self._log.latest()
            except GenerationListingOverflowError:
                self._cleanup.run(None, self.token)
                return "ok", None
            self._cleanup.run(latest, self.token)
        except (OSError, TreeReplacedError):
            return "ok", None
        return ("ok" if self.token in latest.members else "lost"), None


@dataclass(frozen=True, slots=True, kw_only=True)
class _HolderRecord:
    identity: tuple[int, int]
    refreshed: float


__all__ = [
    "HeartbeatOutcome",
    "Mode",
    "Participant",
]
