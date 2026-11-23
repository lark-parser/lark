from __future__ import annotations

__lazy_modules__ = [
    "argparse",
    f"{__spec__.parent}.cache_migration",  # ty: ignore[missing-union-attribute]  # imported modules have a spec
    f"{__spec__.parent}.na",  # ty: ignore[missing-union-attribute]  # imported modules have a spec
    f"{__spec__.parent}.read_only",  # ty: ignore[missing-union-attribute]  # imported modules have a spec
    f"{__spec__.parent}.via_disk_folder",  # ty: ignore[missing-union-attribute]  # imported modules have a spec
    f"{__spec__.parent}.via_tempdir",  # ty: ignore[missing-union-attribute]  # imported modules have a spec
]

import logging
import os
from argparse import ArgumentTypeError
from stat import S_IMODE, S_IRWXG, S_IRWXO, S_ISGID
from typing import TYPE_CHECKING, Final

from .cache_migration import cache_dir_with_migration, make_private_dirs
from .na import AppDataDisabled
from .read_only import ReadOnlyAppData
from .via_disk_folder import AppDataDiskFolder
from .via_tempdir import TempAppData

if TYPE_CHECKING:
    from collections.abc import Mapping

    from .base import AppData

_LOGGER: Final[logging.Logger] = logging.getLogger(__name__)


def make_app_data(folder: str | None, *, read_only: bool, env: Mapping[str, str]) -> AppData:
    """Create the app data store for the given folder, falling back to a temporary one when the folder is unusable.

    :param folder: the folder to use, ``None`` for the default cache directory
    :param read_only: ``True`` to open the folder without writing to it
    :param env: the environment variables, used to find the default folder and the override

    :returns: the app data store

    :raises ArgumentTypeError: when the folder is empty or whitespace
    :raises RuntimeError: when read-only app-data has no default location

    """
    private: Final[bool] = folder is None and not env.get("VIRTUALENV_OVERRIDE_APP_DATA", "").strip()
    if folder is None:
        # A blank override must not resolve to the working directory, which --reset-app-data could delete.
        folder = env.get("VIRTUALENV_OVERRIDE_APP_DATA", "")
        if not folder.strip():
            folder = cache_dir_with_migration(read_only=read_only)
            if folder is None:
                if read_only:
                    reason: Final[str] = (
                        "read-only app data requires an explicit cache path when the default cache is unavailable"
                    )
                    raise RuntimeError(reason)
                _LOGGER.warning("using temporary app-data because the default cache location is unavailable")
                return TempAppData()
    elif not folder.strip():
        # an empty value, often an unset shell variable, resolves to the working directory (on Windows so do spaces)
        # and --reset-app-data would delete it
        msg: Final[str] = f"app data folder {folder!r} must not be empty or whitespace"
        raise ArgumentTypeError(msg)
    folder = os.path.abspath(folder)

    if read_only:
        return ReadOnlyAppData(folder)

    if not _prepare_app_data_folder(folder, private):
        return TempAppData()

    if os.access(folder, os.W_OK):
        return AppDataDiskFolder(folder, private=private)
    _LOGGER.debug("app data folder %s has no write access", folder)
    return TempAppData()


def _prepare_app_data_folder(folder: str, private: bool) -> bool:
    try:
        if private:
            make_private_dirs(folder)
        else:
            os.makedirs(folder, mode=0o777, exist_ok=True)
        if private and os.name == "posix" and not _prepare_permissions(folder):
            return False
    except OSError as exception:
        _LOGGER.info("could not prepare app data folder %s due to %r", folder, exception)
    else:
        _LOGGER.debug("created app data folder %s", folder)
    return True


def _prepare_permissions(folder: str) -> bool:
    info: Final[os.stat_result] = os.stat(folder)
    if info.st_uid not in {os.geteuid(), 0}:
        _LOGGER.warning("using temporary app-data because default cache %s is owned by uid %d", folder, info.st_uid)
        return False
    if info.st_uid != os.geteuid():
        return True
    # setgid marks intentional group sharing; other users must not reach descendants created under a loose umask
    loose: Final[int] = info.st_mode & (S_IRWXO if info.st_mode & S_ISGID else S_IRWXG | S_IRWXO)
    if loose:
        try:
            os.chmod(folder, S_IMODE(info.st_mode) & ~loose)
        except OSError:
            _LOGGER.warning("using temporary app-data because default cache permissions could not be set")
            return False
        _LOGGER.warning(
            "restricted default cache %s to mode %04o; use setgid sharing or an explicit --app-data path to keep "
            "shared access",
            folder,
            S_IMODE(info.st_mode) & ~loose,
        )
    return True


__all__ = [
    "AppDataDisabled",
    "AppDataDiskFolder",
    "ReadOnlyAppData",
    "TempAppData",
    "make_app_data",
]
