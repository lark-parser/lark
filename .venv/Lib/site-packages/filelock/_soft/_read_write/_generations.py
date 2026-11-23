"""Immutable snapshots and commits in the reader/writer generation log."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from importlib.machinery import ModuleSpec

__spec__ = cast("ModuleSpec", __spec__)

__lazy_modules__ = ["contextlib", "pathlib", f"{__spec__.parent}._storage"]

from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from filelock import SoftFileLockProtocolError

from ._storage import (
    GENERATIONS_DIRECTORY,
    HOUSEKEEPING_BATCH,
    MAX_LISTED_NAMES,
    MAX_RECORD_SIZE,
    PROTOCOL,
    TEMPORARY_PREFIX,
    RecordFiles,
    is_token,
    new_token,
)

_GENERATION_DIGITS: Final[int] = 20
_RETAINED_GENERATIONS: Final[int] = 64


class GenerationLog:
    def __init__(self, files: RecordFiles, lock_file: str, root: str) -> None:
        self._files = files
        self.lock_file = lock_file
        self._directory = Path(root, GENERATIONS_DIRECTORY)
        self._epoch_path = str(self._directory / "epoch")
        self._head_path = str(self._directory / "HEAD")
        self._epoch: bytes | None = None
        self._latest: Snapshot | None = None

    def latest(self) -> Snapshot:
        # Compaction or a reset can remove every name between listing and reading. Check once more.
        if (latest := self._find()) is None and (latest := self._find()) is None:
            raise SoftFileLockProtocolError(self.lock_file, None, "generation log names no readable snapshot")
        self._latest = latest
        return latest

    def _find(self) -> Snapshot | None:
        if (epoch := self._incarnation()) != self._epoch:
            self._epoch, self._latest = epoch, None
        named = set(self._list())
        # Generation zero has no on-disk record.
        if self._latest is not None and self._latest.generation:
            named.add(self._latest.generation)
        if head := self._head_generation():
            named.add(head)
        for generation in sorted(named, reverse=True):
            if (start := self._read(generation)) is not None:
                # Generations stay contiguous after HEAD, so one gap there ends the probe.
                return self._probe(start, patience=1 if generation == head else _RETAINED_GENERATIONS)
        newest = max(named, default=0)
        found = self._probe(Snapshot(generation=newest, writer=None, readers=frozenset()))
        return found if found.generation > newest or not named else None

    def _incarnation(self) -> bytes | None:
        if (epoch := self._files.read(self._epoch_path)) is None:
            # Exclusive creation works without hard links. A partial epoch forces the next commit to retry.
            try:
                self._files.create(self._epoch_path, f"{new_token()}\n".encode("ascii"), durable=True)
            except FileExistsError:
                pass
            except FileNotFoundError:
                # A participant recreates a missing directory before publication.
                return None
            epoch = self._files.read(self._epoch_path)
        return epoch

    def _list(self) -> list[int]:
        listed = self._listed()
        # Keeping the reader window contiguous lets a missing generation end a probe.
        del listed[HOUSEKEEPING_BATCH:-_RETAINED_GENERATIONS]
        for generation in listed[:-_RETAINED_GENERATIONS]:
            self._files.unlink(self._path(generation), witness=self._path(listed[-1]))
        return listed[-_RETAINED_GENERATIONS:]

    def _listed(self) -> list[int]:
        if len(names := self._files.listdir(str(self._directory))) > MAX_LISTED_NAMES:
            raise GenerationListingOverflowError(
                self.lock_file, None, f"generation log holds more than {MAX_LISTED_NAMES} names"
            )
        # Superscripts pass isdigit() but fail int(), and fullwidth digits would alias ASCII names.
        return sorted(
            int(name) for name in names if len(name) == _GENERATION_DIGITS and name.isascii() and name.isdigit()
        )

    def _path(self, generation: int) -> str:
        return str(self._directory / self._name(generation))

    @staticmethod
    def _name(generation: int) -> str:
        return f"{generation:0{_GENERATION_DIGITS}d}"

    def _head_generation(self) -> int | None:
        # A crash can tear HEAD because it is only a hint. Readers verify its target.
        if (record := self._head_record()) is None or (snapshot := parse_snapshot(record)) is None:
            return None
        return snapshot.generation

    def _head_record(self) -> bytes | None:
        if (data := self._files.read(self._head_path)) is None:
            return None
        # A delayed HEAD update may belong to a removed log.
        epoch, newline, record = data.partition(b"\n")
        return record if self._valid_epoch() == epoch + newline else None

    def _valid_epoch(self) -> bytes | None:
        epoch = self._epoch
        return epoch if epoch is not None and is_token(epoch.decode("ascii", "replace").removesuffix("\n")) else None

    def _read(self, generation: int) -> Snapshot | None:
        if (data := self._files.read(self._path(generation))) is None:
            return None
        if (snapshot := parse_snapshot(data)) is None or snapshot.generation != generation:
            raise SoftFileLockProtocolError(self.lock_file, self._name(generation), "malformed generation record")
        return snapshot

    def _probe(self, start: Snapshot, patience: int = _RETAINED_GENERATIONS) -> Snapshot:
        latest = start
        generation = start.generation
        limit = generation + 2 * _RETAINED_GENERATIONS
        gap = 0
        # The acquire deadline is checked between probes.
        while gap < patience and generation < limit:
            generation += 1
            if (snapshot := self._read(generation)) is None:
                gap += 1
                continue
            latest = snapshot
            gap = 0
        return latest

    def commit(self, successor: Snapshot) -> bool:
        try:
            return self._publish_successor(successor)
        except GenerationListingOverflowError:
            # A peer may already have extended the record published before the listing failed.
            return False

    def _publish_successor(self, successor: Snapshot) -> bool:
        # Compaction may free this slot during publication. A surviving predecessor can itself be a delayed write.
        if not self._extends_the_log(successor.generation):
            return False
        if not self._publish(self._path(successor.generation), data := successor.encode()):
            return False
        newest = max([*self._listed(), self._head_generation() or 0])
        extends = self._extends_the_log(successor.generation)
        if self._files.read(self._epoch_path) != self._epoch:
            # Another log may now use this generation number.
            return False
        if newest - successor.generation >= _RETAINED_GENERATIONS:
            self._files.unlink(self._path(successor.generation), witness=self._path(newest))
            return False
        if not extends:
            # A peer may have extended the record, so only compaction can free its slot.
            return False
        self._latest = successor
        # A failed HEAD update costs readers a probe. A delayed commit must not move HEAD backward.
        with suppress(OSError):
            if (epoch := self._valid_epoch()) is not None and (self._head_generation() or 0) < successor.generation:
                self._files.write_head(self._head_path, f"{TEMPORARY_PREFIX}{new_token()}", epoch + data)
        if (expired := successor.generation - _RETAINED_GENERATIONS - 1) > 0:
            self._compact_through(expired, successor.generation)
        return True

    def _extends_the_log(self, generation: int) -> bool:
        # A missing predecessor leaves a free slot after compaction. HEAD distinguishes a reused first slot.
        if generation > 1:
            return self._files.read(self._path(generation - 1)) is not None
        return self._head_record() is None

    def _publish(self, target: str, data: bytes) -> bool:
        temporary = str(self._directory / f"{TEMPORARY_PREFIX}{new_token()}")
        try:
            self._files.create(temporary, data, durable=True)
        except FileNotFoundError:
            # A surviving holder record would prevent the next acquire from recreating gen/.
            self._files.prepare(str(self._directory.parent), force=True)
            return False
        try:
            # A reset before staging may put this file in another log. A later reset removes its source name.
            if self._files.read(self._epoch_path) != self._epoch:
                return False
            try:
                return self._files.link(temporary, target)
            except FileNotFoundError:
                if self._files.read(temporary) is not None:
                    raise
                return False
        finally:
            self._files.unlink(temporary)

    def _compact_through(self, expired: int, newest: int) -> None:
        # Removing oldest first leaves no gap below a stalled committer's record.
        oldest = expired
        while oldest > 1 and self._files.read(self._path(oldest - 1)) is not None:
            oldest -= 1
            if expired - oldest >= HOUSEKEEPING_BATCH:
                # Listings can prune a larger backlog without leaving a gap.
                return
        for generation in range(oldest, expired + 1):
            self._files.unlink(self._path(generation), witness=self._path(newest))


@dataclass(frozen=True, slots=True, kw_only=True)
class Snapshot:
    generation: int
    writer: str | None
    readers: frozenset[str]

    @property
    def members(self) -> frozenset[str]:
        return self.readers if self.writer is None else self.readers | {self.writer}

    def encode(self) -> bytes:
        lines = [PROTOCOL, f"generation={self.generation}"]
        if self.writer is not None:
            lines.append(f"writer={self.writer}")
        lines.extend(f"reader={token}" for token in sorted(self.readers))
        return "".join(f"{line}\n" for line in lines).encode("ascii")


class GenerationListingOverflowError(SoftFileLockProtocolError):
    pass


def parse_snapshot(data: bytes) -> Snapshot | None:
    if not data or len(data) > MAX_RECORD_SIZE:
        return None
    try:
        lines = data.decode("ascii").split("\n")
    except UnicodeDecodeError:
        return None
    if lines[0] != PROTOCOL or lines[-1]:
        return None
    generation: int | None = None
    writer: str | None = None
    readers: set[str] = set()
    for line in lines[1:-1]:
        key, _, value = line.partition("=")
        if (
            key == "generation"
            and generation is None
            and len(value) <= _GENERATION_DIGITS
            and value.isdigit()
            and str(int(value)) == value
        ):
            generation = int(value)
        elif key == "writer" and writer is None and is_token(value):
            writer = value
        elif key == "reader" and is_token(value) and value not in readers:
            readers.add(value)
        else:
            return None
    return None if generation is None else Snapshot(generation=generation, writer=writer, readers=frozenset(readers))


__all__ = [
    "GenerationListingOverflowError",
    "GenerationLog",
    "Snapshot",
    "parse_snapshot",
]
