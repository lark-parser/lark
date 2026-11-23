"""holds locking functionality that works across processes."""

from __future__ import annotations

__lazy_modules__ = ["pathlib"]

import logging
import os
from abc import ABC, abstractmethod
from contextlib import contextmanager, suppress
from pathlib import Path
from threading import Lock, RLock
from typing import TYPE_CHECKING, Final

from filelock import FileLock, Timeout

if TYPE_CHECKING:
    from collections.abc import Generator
    from types import TracebackType

LOGGER: Final[logging.Logger] = logging.getLogger(__name__)  # simplint: ignore[module-variable-prefix]  # existing name


_LOCK_STORE = {}  # simplint: ignore[missing-final]  # ty infers a different value type on Python 3.9 when annotated
_STORE_LOCK: Final[Lock] = Lock()


class PathLockBase(ABC):
    """Base of the folder locks, which lock keys within one folder.

    :param folder: the folder the locks live in

    :var path: the folder, resolved when it exists

    """

    def __init__(self, folder: str | Path) -> None:
        path = Path(folder)
        self.path = path.resolve() if path.exists() else path

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.path})"

    def __truediv__(self, other: str) -> PathLockBase:
        return type(self)(self.path / other)

    @abstractmethod
    def __enter__(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def __exit__(
        self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: TracebackType | None
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    @contextmanager
    # the flag is part of the lock_for_key interface that every lock class implements
    def lock_for_key(self, name: str, no_block: bool = False) -> Generator[None, None, None]:  # ruff:ignore[boolean-default-value-positional-argument]
        """Hold the lock of ``name`` within this folder, failing instead of waiting when ``no_block`` is set.

        :param name: the key to lock
        :param no_block: ``True`` to fail instead of waiting for the lock

        :returns: a context manager holding the lock

        """
        raise NotImplementedError

    @abstractmethod
    @contextmanager
    def non_reentrant_lock_for_key(self, name: str) -> Generator[None, None, None]:
        """Hold the lock of ``name`` within this folder, which the same thread may not take again.

        :param name: the key to lock

        :returns: a context manager holding the lock

        """
        raise NotImplementedError


class ReentrantFileLock(PathLockBase):
    """Folder lock whose per-key locks the same thread may take again, with the folder path as its path.

    :param folder: the folder to lock

    """

    def __init__(self, folder: str | Path) -> None:
        super().__init__(folder)
        self._lock = None

    def __del__(self) -> None:
        self._del_lock(self._lock)

    @staticmethod
    def _del_lock(lock: _CountedFileLock | None) -> None:
        if lock is not None:
            with _STORE_LOCK, lock.thread_safe:
                if lock.count == 0:
                    _LOCK_STORE.pop(lock.lock_file, None)

    def __enter__(self) -> None:
        self._lock = self._create_lock()
        self._lock_file(self._lock)

    def _create_lock(self, name: str = "") -> _CountedFileLock:
        lock_file = str(self.path / f"{name}.lock")
        with _STORE_LOCK:
            if lock_file not in _LOCK_STORE:
                _LOCK_STORE[lock_file] = _CountedFileLock(lock_file)
            return _LOCK_STORE[lock_file]

    # no_block is passed positionally by lock_for_key, the signature stays
    def _lock_file(self, lock: _CountedFileLock, no_block: bool = False) -> None:  # ruff:ignore[boolean-default-value-positional-argument]
        # multiple processes might be trying to get a first lock... so we cannot check if this directory exist without
        # a lock, but that lock might then become expensive, and it's not clear where that lock should live.
        # Instead here we just ignore if we fail to create the directory.
        with suppress(OSError):
            os.makedirs(str(self.path), exist_ok=True)

        try:
            lock.acquire(0.0001)
        except Timeout:
            if no_block:
                raise
            LOGGER.debug("lock file %s present, will block until released", lock.lock_file)
            lock.release()  # release the acquire try from above
            lock.acquire()

    def __exit__(
        self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: TracebackType | None
    ) -> None:
        # _lock is set by __enter__, so it is not None when __exit__ runs
        self._release(self._lock)  # ty: ignore[invalid-argument-type]
        self._del_lock(self._lock)
        self._lock = None

    @staticmethod
    def _release(lock: _CountedFileLock) -> None:
        lock.release()

    @contextmanager
    # the flag is passed through to _lock_file, so every lock class shares the signature
    def lock_for_key(self, name: str, no_block: bool = False) -> Generator[None, None, None]:  # ruff:ignore[boolean-default-value-positional-argument]
        """Hold the lock for a key, taking it again when this thread already holds it.

        :param name: the key to lock
        :param no_block: ``True`` to fail instead of waiting when the lock is held elsewhere

        :yields: nothing

        """
        lock = self._create_lock(name)
        try:
            with self._lock_and_yield(lock, no_block):
                yield
        finally:
            self._del_lock(lock)
            lock = None

    @contextmanager
    def _lock_and_yield(self, lock: _CountedFileLock, no_block: bool) -> Generator[None, None, None]:
        self._lock_file(lock, no_block)
        try:
            yield
        finally:
            self._release(lock)

    @contextmanager
    def non_reentrant_lock_for_key(self, name: str) -> Generator[None, None, None]:
        """Hold a lock for a key that this thread must not take again.

        :param name: the key to lock

        :yields: nothing

        """
        with _CountedFileLock(str(self.path / f"{name}.lock")):
            yield


class _CountedFileLock(FileLock):
    def __init__(self, lock_file: str) -> None:
        parent = os.path.dirname(lock_file)
        with suppress(OSError):
            os.makedirs(parent, exist_ok=True)

        super().__init__(lock_file)
        self.count = 0
        self.thread_safe = RLock()

    # filelock's acquire takes poll_interval as float | None and more keyword arguments, this override narrows them
    def acquire(  # ty: ignore[incompatible-method-override]
        self,
        timeout: float | None = None,
        poll_interval: float = 0.05,
    ) -> None:
        if not self.thread_safe.acquire(timeout=-1 if timeout is None else timeout):
            raise Timeout(self.lock_file)
        if self.count == 0:
            try:
                super().acquire(timeout, poll_interval)
            except BaseException:
                self.thread_safe.release()
                raise
        self.count += 1

    # force is a flag of the lock API, callers set it by keyword
    def release(self, force: bool = False) -> None:  # ruff:ignore[boolean-default-value-positional-argument]
        with self.thread_safe:
            if self.count > 0:
                if self.count == 1:
                    super().release(force=force)
                self.count -= 1
                # Each acquire takes the RLock, including recursive acquisitions.
                self.thread_safe.release()


class NoOpFileLock(PathLockBase):
    """Lock that takes no lock, for folders that are read only."""

    def __enter__(self) -> None:
        raise NotImplementedError

    def __exit__(
        self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: TracebackType | None
    ) -> None:
        raise NotImplementedError

    @contextmanager
    # the no-op lock ignores its arguments, the signature matches the lock interface
    def lock_for_key(self, name: str, no_block: bool = False) -> Generator[None, None, None]:  # ruff:ignore[unused-method-argument, boolean-default-value-positional-argument]
        """Hold no lock, as the folder is read only.

        :param name: the key, ignored since no lock is taken
        :param no_block: ignored since no lock is taken

        :yields: nothing

        """
        yield

    @contextmanager
    # the no-op lock ignores the name, the signature matches the lock interface
    def non_reentrant_lock_for_key(self, name: str) -> Generator[None, None, None]:  # ruff:ignore[unused-method-argument]
        """Hold no lock, as the folder is read only.

        :param name: the key, ignored since no lock is taken

        :yields: nothing

        """
        yield


__all__ = [
    "NoOpFileLock",
    "PathLockBase",
    "ReentrantFileLock",
    "Timeout",
]
