from __future__ import annotations

__lazy_modules__ = [
    "tempfile",
    "virtualenv.util.path",
]

import logging
from tempfile import mkdtemp
from typing import TYPE_CHECKING, Final

from virtualenv.util.path import safe_delete_read_only

from .via_disk_folder import AppDataDiskFolder

if TYPE_CHECKING:
    from typing import NoReturn

LOGGER: Final[logging.Logger] = logging.getLogger(__name__)  # simplint: ignore[module-variable-prefix]  # existing name


class TempAppData(AppDataDiskFolder):
    """Temporary app data folder, created on start and removed on close.

    :var transient: always ``True``, the data is removed on close
    :var can_update: always ``False``, the data is empty to start with

    """

    transient = True
    can_update = False

    def __init__(self) -> None:
        super().__init__(folder=mkdtemp())
        LOGGER.debug("created temporary app data folder %s", self.lock.path)

    def reset(self) -> None:
        """This is a temporary folder, is already empty to start with."""

    def close(self) -> None:
        """Remove the temporary folder."""
        LOGGER.debug("remove temporary app data folder %s", self.lock.path)
        safe_delete_read_only(self.lock.path)

    def embed_update_log(self, distribution: str, for_py_version: str) -> NoReturn:
        """Refuse to provide an embed update log, since it is not kept for temporary folders.

        :param distribution: the distribution name
        :param for_py_version: the Python version

        :raises NotImplementedError: always

        """
        raise NotImplementedError


__all__ = [
    "TempAppData",
]
