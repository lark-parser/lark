from __future__ import annotations

__lazy_modules__ = ["virtualenv.util.lock"]

import os.path
from typing import TYPE_CHECKING

from virtualenv.util.lock import NoOpFileLock

from .via_disk_folder import AppDataDiskFolder, PyInfoStoreDisk

if TYPE_CHECKING:
    from pathlib import Path
    from typing import NoReturn


class ReadOnlyAppData(AppDataDiskFolder):
    """App data folder that is only read, for folders the user cannot write to.

    :param folder: the existing folder to read from

    :raises RuntimeError: when the folder does not exist

    :var can_update: always ``False``, the data cannot be updated
    :var lock: the lock that never locks, since nothing is written

    """

    can_update = False

    def __init__(self, folder: str) -> None:
        if not os.path.isdir(folder):
            msg = f"read-only app data directory {folder} does not exist"
            raise RuntimeError(msg)
        super().__init__(folder)
        self.lock = NoOpFileLock(folder)

    def reset(self) -> None:
        """Refuse to reset, since the folder is read-only.

        :raises RuntimeError: always

        """
        msg = "read-only app data does not support reset"
        raise RuntimeError(msg)

    def py_info_clear(self) -> None:
        """Refuse to clear the python info, since the folder is read-only.

        :raises NotImplementedError: always

        """
        raise NotImplementedError

    def py_info(self, path: Path) -> _PyInfoStoreDiskReadOnly:
        """Return a read-only store for the python info of the path.

        :param path: the interpreter path the info is for

        :returns: the read-only python info store

        """
        return _PyInfoStoreDiskReadOnly(self.py_info_at, path)

    def embed_update_log(self, distribution: str, for_py_version: str) -> NoReturn:
        """Refuse to provide an embed update log, since it is not kept for read-only folders.

        :param distribution: the distribution name
        :param for_py_version: the Python version

        :raises NotImplementedError: always

        """
        raise NotImplementedError


class _PyInfoStoreDiskReadOnly(PyInfoStoreDisk):
    # a read-only store always refuses the write, so the content is unused
    def write(self, content: str) -> NoReturn:  # ruff:ignore[unused-method-argument]
        msg = "read-only app data python info cannot be updated"
        raise RuntimeError(msg)


__all__ = [
    "ReadOnlyAppData",
]
