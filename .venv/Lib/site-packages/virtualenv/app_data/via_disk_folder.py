r"""A rough layout of the current storage goes as:

::

    virtualenv-app-data
    ├── py - <version> <cache information about python interpreters>
    │  └── *.json/lock
    ├── wheel <cache wheels used for seeding>
    │   ├── house
    │   │   └── <index> -> verified PyPI or a custom index configuration
    │   └── <python major.minor> -> 3.9
    │       ├── img-<version>
    │       │   └── image
    │       │           └── <install class> -> CopyPipInstall / SymlinkPipInstall
    │       │               └── <wheel sha256>
    │       └── embed
    │           └── 4/<index> -> json format version and index
    │               └── *.json -> for every distribution contains data about newer embed versions and releases

    └─── unzip <in zip app we cannot refer to some internal files, so first extract them>
         └── <virtualenv version>
             ├── py_info.py
             ├── debug.py
             └── _virtualenv.py

"""  # ruff:ignore[missing-terminal-punctuation]  # the directory tree is a literal block that ends the docstring

from __future__ import annotations

__lazy_modules__ = [
    "hashlib",
    "json",
    "virtualenv.util.lock",
    "virtualenv.util.path",
    "virtualenv.util.zipapp",
    "virtualenv.version",
    f"{__spec__.parent}.cache_migration",  # ty: ignore[missing-union-attribute]  # imported modules have a spec
]

import json
import logging
import os
from abc import ABC
from contextlib import contextmanager, suppress
from hashlib import sha256
from stat import S_IMODE, S_ISGID
from typing import TYPE_CHECKING, Any, Final

from virtualenv.util.lock import ReentrantFileLock
from virtualenv.util.path import safe_delete_read_only
from virtualenv.util.zipapp import extract
from virtualenv.version import __version__

from .base import AppData, ContentStore
from .cache_migration import make_private_dirs

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

LOGGER: Final[logging.Logger] = logging.getLogger(__name__)  # simplint: ignore[module-variable-prefix]  # existing name


class AppDataDiskFolder(AppData):
    """Store the application data on the disk within a folder layout.

    :param folder: the folder to store the application data in
    :param private: whether reset must restore the default cache's access policy

    :var transient: always ``False``, the data persists across runs
    :var reuse_custom_wheels: whether the directory was selected explicitly
    :var can_update: always ``True``, the data can be updated
    :var lock: the lock guarding the folder

    """

    transient = False
    can_update = True

    def __init__(self, folder: str, *, private: bool = False) -> None:
        self.lock = ReentrantFileLock(folder)
        self._private = private
        self.reuse_custom_wheels = not private

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.lock.path})"

    def __str__(self) -> str:
        return str(self.lock.path)

    @property
    def house(self) -> Path:
        """The wheel house folder, created when first accessed, holding the downloaded wheels."""
        path = self.lock.path / "wheel" / "house" / self.wheel_index
        path.mkdir(parents=True, exist_ok=True)
        return path

    def reset(self) -> None:
        """Discard stored data and restore default cache permissions when needed."""
        LOGGER.debug("reset app data folder %s", self.lock.path)
        info: os.stat_result | None = None
        if self._private and os.name == "posix":
            with suppress(FileNotFoundError):
                info = os.stat(self.lock.path)
        safe_delete_read_only(self.lock.path)
        if self._private:
            make_private_dirs(str(self.lock.path))
            if info is not None and info.st_mode & S_ISGID:
                try:
                    os.chown(self.lock.path, -1, info.st_gid)
                    os.chmod(self.lock.path, S_IMODE(info.st_mode))
                except OSError as exception:
                    LOGGER.warning("keeping reset app data folder %s private: %r", self.lock.path, exception)

    def close(self) -> None:
        """Do nothing."""

    @contextmanager
    def locked(self, path: Path) -> Generator[None]:
        """Hold the lock for the path while the caller uses it.

        :param path: the path to lock

        :yields: nothing

        """
        # the lock's / operator takes a str key, and path here is a Path
        path_lock = self.lock / path  # ty: ignore[unsupported-operator]
        with path_lock:
            yield path_lock.path

    @contextmanager
    def extract(self, path: Path, to_folder: Path | None) -> Generator[Path]:
        """Extract the file into its folder, reusing an earlier extraction.

        :param path: the file to extract
        :param to_folder: a callable returning the folder to extract into, ``None`` for the default ``unzip`` folder

        :yields: the path of the extracted file

        """
        # callers pass a callable for to_folder, despite the Path | None annotation; use the app data's own lock type,
        # so a read-only app data does not create lock files in the folder
        root = type(self.lock)(to_folder()) if to_folder is not None else self.lock / "unzip" / __version__  # ty: ignore[not-callable]
        with root.lock_for_key(path.name):
            dest = root.path / path.name
            if not dest.exists():
                extract(path, dest)
            yield dest

    def py_info(self, path: Path) -> PyInfoStoreDisk:
        """Return the store of the python info for the given interpreter path.

        :param path: the interpreter path the info is for

        :returns: the python info store

        """
        return PyInfoStoreDisk(self.py_info_at, path)

    @property
    def py_info_at(self) -> ReentrantFileLock:
        """The lock guarding the python info folder."""
        # the lock's / operator returns PathLockBase, not the ReentrantFileLock promised here
        return self.lock / "py_info" / "5"  # ty: ignore[invalid-explicit-return]

    def py_info_clear(self) -> None:
        """clear py info."""
        py_info_folder = self.py_info_at
        with py_info_folder:
            for filename in py_info_folder.path.iterdir():
                if filename.suffix == ".json":
                    with py_info_folder.lock_for_key(filename.stem):
                        if filename.exists():
                            filename.unlink()

    def embed_update_log(self, distribution: str, for_py_version: str) -> EmbedDistributionUpdateStoreDisk:
        """Return the store of the embed update log for a distribution and Python version.

        :param distribution: the distribution name
        :param for_py_version: the Python version

        :returns: the embed update log store

        """
        root = self.lock / "wheel" / for_py_version / "embed" / "4" / self.wheel_index
        # The lock preserves its concrete type when joined.
        return EmbedDistributionUpdateStoreDisk(root, distribution)  # ty: ignore[invalid-argument-type]

    def wheel_image(self, for_py_version: str, name: str) -> Path:
        """Return the path of an installed wheel image.

        :param for_py_version: the Python version
        :param name: the name of the image

        :returns: the path of the image

        """
        return self.lock.path / "wheel" / for_py_version / "image" / "1" / name


class JSONStoreDisk(ContentStore, ABC):
    """JSON file store kept in a folder, with one file per key.

    :param in_folder: the lock of the folder holding the files
    :param key: the name of the file without suffix
    :param msg_args: the leading arguments of the debug messages about the file

    :var in_folder: the lock of the folder holding the files
    :var key: the name of the file without suffix
    :var msg_args: the leading arguments of the debug messages about the file

    """

    def __init__(self, in_folder: ReentrantFileLock, key: str, msg_args: tuple[str, ...]) -> None:
        self.in_folder = in_folder
        self.key = key
        self.msg_args = (*msg_args, self.file)

    @property
    def file(self) -> Path:
        """The path of the JSON file."""
        return self.in_folder.path / f"{self.key}.json"

    def exists(self) -> bool:
        """Whether the JSON file exists.

        :returns: ``True`` when the file exists

        """
        return self.file.exists()

    def read(self) -> Any:  # ruff:ignore[any-type]  # the stored JSON document may be any type
        """Read the stored JSON document, treating a missing or unreadable file as absent.

        :returns: the decoded document, ``None`` when there is none

        """
        data, bad_format = None, False
        try:
            data = json.loads(self.file.read_text(encoding="utf-8"))
        except ValueError:
            bad_format = True
        # an unreadable file is treated as missing, so the read does not fail
        except Exception:  # ruff:ignore[blind-except, try-except-pass]
            pass
        else:
            LOGGER.debug("got %s %s from %s", *self.msg_args)
            return data
        if bad_format:
            with suppress(OSError):  # reading and writing on the same file may cause race on multiple processes
                self.remove()
        return None

    def remove(self) -> None:
        """Delete the JSON file."""
        self.file.unlink()
        LOGGER.debug("removed %s %s at %s", *self.msg_args)

    @contextmanager
    def locked(self) -> Generator[None]:
        """Hold the lock for the key while the caller uses it.

        :yields: nothing

        """
        with self.in_folder.lock_for_key(self.key):
            yield

    def write(self, content: Any) -> None:  # ruff:ignore[any-type]  # stores any JSON-serializable content
        """Store the content as JSON, creating the folder when needed.

        :param content: the JSON-serializable content to store

        """
        self.file.parent.mkdir(parents=True, exist_ok=True)
        self.file.write_text(json.dumps(content, sort_keys=True, indent=2), encoding="utf-8")
        LOGGER.debug("wrote %s %s at %s", *self.msg_args)


class PyInfoStoreDisk(JSONStoreDisk):
    """Store of the python info of one interpreter path, keyed by a hash of the path.

    :param in_folder: the lock of the folder holding the files
    :param path: the interpreter path the info is for

    :var in_folder: the lock of the folder holding the files
    :var key: the hash of the interpreter path
    :var msg_args: the leading arguments of the debug messages about the file

    """

    def __init__(self, in_folder: ReentrantFileLock, path: Path) -> None:
        # msg_args carries the Path for the log message, but is typed as str
        super().__init__(in_folder, sha256(str(path).encode("utf-8")).hexdigest(), ("python info of", path))  # ty: ignore[invalid-argument-type]


class EmbedDistributionUpdateStoreDisk(JSONStoreDisk):  # simplint: ignore[missing-from-all]  # existing local type
    """Update log of an embedded distribution, kept as a JSON file in the app data folder.

    :param in_folder: the lock of the folder the log lives in
    :param distribution: the name of the distribution

    """

    def __init__(self, in_folder: ReentrantFileLock, distribution: str) -> None:
        super().__init__(
            in_folder,
            distribution,
            ("embed update of distribution", distribution),
        )


__all__ = [
    "AppDataDiskFolder",
    "JSONStoreDisk",
    "PyInfoStoreDisk",
]
