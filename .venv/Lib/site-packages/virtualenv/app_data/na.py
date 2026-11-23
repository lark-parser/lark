from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING

from .base import AppData, ContentStore

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path
    from typing import Any, NoReturn


class AppDataDisabled(AppData):
    """No application cache available (most likely as we don't have write permissions).

    :var transient: always ``True``, nothing is persisted
    :var can_update: always ``False``, there is nothing to update
    :var error: the error raised on every access to the cache

    """

    transient = True
    can_update = False

    error = RuntimeError("no app data folder available, probably no write access to the folder")

    def __init__(self) -> None:
        pass

    @property
    def house(self) -> NoReturn:
        """The app data folder, which is never available, so every access raises.

        :raises RuntimeError: always

        """
        raise self.error

    def close(self) -> None:
        """Do nothing."""

    def reset(self) -> None:
        """Do nothing."""

    # the no-op store ignores the path, the signature must match the store interface
    def py_info(self, path: Path) -> ContentStoreNA:  # ruff:ignore[unused-method-argument]
        """Return a store that holds nothing and ignores the path.

        :param path: the path the store would be for, ignored

        :returns: the no-op store

        """
        return ContentStoreNA()

    # the no-op store ignores the distribution, the signature must match the store interface
    def embed_update_log(self, distribution: str, for_py_version: str) -> ContentStoreNA:  # ruff:ignore[unused-method-argument]
        """Return a store that holds nothing and ignores the distribution.

        :param distribution: the distribution name, ignored
        :param for_py_version: the Python version, ignored

        :returns: the no-op store

        """
        return ContentStoreNA()

    # the no-op store never extracts, so the arguments are unused
    def extract(self, path: Path, to_folder: Path | None) -> NoReturn:  # ruff:ignore[unused-method-argument]
        """Refuse to extract, since no app data folder is available.

        :param path: the file to extract, ignored
        :param to_folder: the folder to extract into, ignored

        :raises RuntimeError: always

        """
        raise self.error

    @contextmanager
    # the no-op store takes no lock, so the path is unused
    def locked(self, path: Path) -> Generator[None]:  # ruff:ignore[unused-method-argument]
        """Do nothing.

        :param path: the path to lock, ignored since no lock is taken

        :yields: nothing

        """
        yield

    # the no-op store never has an image, so the arguments are unused
    def wheel_image(self, for_py_version: str, name: str) -> NoReturn:  # ruff:ignore[unused-method-argument]
        """Refuse to provide a wheel image, since no app data folder is available.

        :param for_py_version: the Python version, ignored
        :param name: the image name, ignored

        :raises RuntimeError: always

        """
        raise self.error

    def py_info_clear(self) -> None:
        """Nothing to clear."""


class ContentStoreNA(ContentStore):
    """Store that holds nothing: reads return ``None`` and writes are discarded."""

    def exists(self) -> bool:
        """Always ``False``, since nothing is stored.

        :returns: ``False``

        """
        return False

    def read(self) -> None:
        """Nothing to read."""
        return

    # matches the base store's Any content, which this no-op store discards
    def write(self, content: Any) -> None:  # ruff:ignore[any-type]
        """Nothing to write.

        :param content: the content to write, discarded

        """

    def remove(self) -> None:
        """Nothing to remove."""

    @contextmanager
    def locked(self) -> Generator[None]:
        """Take no lock, since nothing is stored.

        :yields: nothing

        """
        yield


__all__ = [
    "AppDataDisabled",
    "ContentStoreNA",
]
