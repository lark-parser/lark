"""Cache Protocol and built-in implementations for Python interpreter discovery."""

from __future__ import annotations

import json
import logging
import os
import stat
from contextlib import contextmanager, suppress
from hashlib import sha256
from os import fsencode
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import TYPE_CHECKING, Final, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Generator

_LOGGER: Final[logging.Logger] = logging.getLogger(__name__)


@runtime_checkable
class ContentStore(Protocol):
    """A store for reading and writing cached content."""

    def exists(self) -> bool:
        """
        Return whether the cached content exists.

        :returns: ``True`` if the content is cached, ``False`` otherwise.
        """
        ...

    def read(self) -> dict | None:
        """
        Read the cached content, or ``None`` if unavailable or corrupt.

        :returns: the cached content, or ``None``.
        """
        ...

    def write(self, content: dict) -> None:
        """
        Persist *content* to the store.

        :param content: interpreter metadata to cache.
        """
        ...

    def remove(self) -> None:
        """Delete the cached content."""
        ...

    @contextmanager
    def locked(self) -> Generator[None]:
        """
        Context manager that acquires an exclusive lock on this store.

        :returns: a context manager; the lock is held inside its ``with`` block.
        """
        ...


@runtime_checkable
class PyInfoCache(Protocol):
    """Cache interface for Python interpreter information."""

    def py_info(self, path: Path) -> ContentStore:
        """
        Return the content store for the interpreter at *path*.

        :param path: absolute path to a Python executable.
        :returns: the content store for *path*.
        """
        ...

    def py_info_clear(self) -> None:
        """Remove all cached interpreter information."""
        ...


class DiskCache:
    """
    File-system based Python interpreter info cache (``<root>/py_info/4/<sha256>.json``).

    :param root: root directory for the on-disk cache.
    """

    def __init__(self, root: Path) -> None:
        self._root = Path(os.path.abspath(root))  # ruff:ignore[os-path-abspath]  # resolve() follows untrusted links

    def py_info(self, path: Path) -> ContentStore:
        """
        Return the content store for the interpreter at *path*.

        :param path: absolute path to a Python executable.
        :returns: the content store for *path*.
        """
        if not self._trusted_folder():
            return NoOpContentStore()
        return DiskContentStore(self._py_info_dir, sha256(fsencode(path)).hexdigest())

    def _trusted_folder(self) -> bool:
        if not hasattr(os, "geteuid"):
            return True
        user_id = os.geteuid()
        folder = self._py_info_dir
        private = {self._root, folder.parent, folder}
        for candidate in (*reversed(folder.parents), folder):
            try:
                try:
                    status = candidate.lstat()
                except FileNotFoundError:
                    candidate.mkdir(exist_ok=True)
                    status = candidate.lstat()
            except OSError:
                _LOGGER.warning("not caching in %s", candidate, exc_info=True)
                return False
            if (
                not stat.S_ISDIR(status.st_mode)
                or status.st_uid not in {user_id, 0}
                or (status.st_mode & 0o022 and (candidate in private or not status.st_mode & stat.S_ISVTX))
            ):
                _LOGGER.warning("not caching in untrusted directory %s", candidate)
                return False
        return True

    @property
    def _py_info_dir(self) -> Path:
        return self._root / "py_info" / "4"

    def py_info_clear(self) -> None:
        """Remove all cached interpreter information."""
        folder = self._py_info_dir
        if folder.exists() and self._trusted_folder():
            for entry in folder.iterdir():
                if entry.suffix == ".json":
                    with suppress(OSError):
                        entry.unlink()


class NoOpContentStore(ContentStore):
    # Content store that does nothing -- implements ContentStore protocol.
    def exists(self) -> bool:  # ruff:ignore[no-self-use] cache protocol
        return False

    def read(self) -> dict | None:  # ruff:ignore[no-self-use] cache protocol
        return None

    def write(self, content: dict) -> None:
        pass

    def remove(self) -> None:
        pass

    @contextmanager
    def locked(self) -> Generator[None]:  # ruff:ignore[no-self-use] cache protocol
        yield


class DiskContentStore:
    # JSON file-based content store with file locking.
    def __init__(self, folder: Path, key: str) -> None:
        self._folder = folder
        self._key = key

    def exists(self) -> bool:
        return self._file.exists()

    @property
    def _file(self) -> Path:
        return self._folder / f"{self._key}.json"

    def read(self) -> dict | None:
        data, bad_format = None, False
        try:
            data, bad_format = self._read_entry()
        except (ValueError, RecursionError):
            bad_format = True
        except OSError:
            _LOGGER.debug("failed to read %s", self._file, exc_info=True)
            bad_format = self._file.is_symlink()
        else:
            if not bad_format:
                _LOGGER.debug("got python info from %s", self._file)
                return data
        if bad_format:
            with suppress(OSError):
                self.remove()
        return None

    def _read_entry(self) -> tuple[dict | None, bool]:
        with open(self._file, encoding="utf-8", opener=self._open_entry) as file:
            status = os.fstat(file.fileno())
            if not stat.S_ISREG(status.st_mode) or (
                hasattr(os, "geteuid") and (status.st_uid not in {os.geteuid(), 0} or status.st_mode & 0o022)
            ):
                _LOGGER.warning("ignoring untrusted cache entry at %s", self._file)
                return None, True
            # A 1 MiB query can expand to 12 MiB when supplementary Unicode is escaped.
            if status.st_size > 16 << 20:
                _LOGGER.warning("ignoring oversized cache entry at %s", self._file)
                return None, True
            return json.load(file), False

    @staticmethod
    def _open_entry(path: str, flags: int) -> int:
        return os.open(path, flags | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))

    def remove(self) -> None:
        with suppress(OSError):
            self._file.unlink()
        _LOGGER.debug("removed python info at %s", self._file)

    def write(self, content: dict) -> None:
        self._folder.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self._folder, prefix=f".{self._key}.", delete=False
            ) as file:
                temporary = Path(file.name)
                # Compact encoding avoids indentation growth and the streaming encoder's recursion limit.
                file.write(json.dumps(content, sort_keys=True))
            temporary.replace(self._file)
        except OSError:
            _LOGGER.debug("failed to write %s", self._file, exc_info=True)
        else:
            _LOGGER.debug("wrote python info at %s", self._file)
        finally:
            if temporary is not None:
                with suppress(OSError):
                    temporary.unlink(missing_ok=True)

    @contextmanager
    def locked(self) -> Generator[None]:
        from filelock import FileLock  # ruff:ignore[import-outside-top-level] filelock is needed only when locking

        self._folder.mkdir(parents=True, exist_ok=True)
        if os.name == "posix":
            group_shared = bool(self._folder.stat().st_mode & stat.S_IWGRP)
            lock_folder = self._folder / "locks-v2"
            lock_folder.mkdir(mode=0o770 if group_shared else 0o700, exist_ok=True)
            lock = FileLock(str(lock_folder / f"{self._key}.lock"), mode=0o660 if group_shared else 0o600)
        else:
            lock = FileLock(str(self._folder / f"{self._key}.lock"))
        with lock:
            yield


class NoOpCache(PyInfoCache):
    # Cache that does nothing -- implements PyInfoCache protocol.
    def py_info(self, path: Path) -> NoOpContentStore:  # ruff:ignore[unused-method-argument, no-self-use] protocol
        return NoOpContentStore()

    def py_info_clear(self) -> None:
        pass


__all__ = [
    "ContentStore",
    "DiskCache",
    "DiskContentStore",
    "NoOpCache",
    "NoOpContentStore",
    "PyInfoCache",
]
