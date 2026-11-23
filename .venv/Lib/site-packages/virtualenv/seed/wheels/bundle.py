from __future__ import annotations

__lazy_modules__ = [
    f"{__spec__.parent}.embed",  # ty: ignore[missing-union-attribute]  # imported modules have a spec
    f"{__spec__.parent}.periodic_update",  # ty: ignore[missing-union-attribute]  # imported modules have a spec
    f"{__spec__.parent}.util",  # ty: ignore[missing-union-attribute]  # imported modules have a spec
]

from typing import TYPE_CHECKING

from .embed import get_embed_wheel
from .periodic_update import periodic_update
from .util import Version, Wheel, discover_wheels

if TYPE_CHECKING:
    from pathlib import Path

    from virtualenv.app_data.base import AppData


# the bundle lookup takes each search input separately, as the callers pass them
def from_bundle(  # ruff:ignore[too-many-arguments]
    distribution: str,
    version: str | None,
    for_py_version: str,
    search_dirs: list[Path],
    app_data: AppData,
    do_periodic_update: bool,
    env: dict[str, str],
) -> Wheel | None:
    """Load the bundled wheel to a cache directory.

    :param distribution: the distribution name, for example ``pip``
    :param version: the requested version, ``None`` when unpinned
    :param for_py_version: the Python version the wheel must support, as ``major.minor``
    :param search_dirs: extra directories searched for a newer wheel
    :param app_data: the application data folder
    :param do_periodic_update: ``True`` to check the index for a wheel newer than the bundled one
    :param env: the environment variables the update check runs with

    :returns: the wheel to seed with, or ``None`` when there is none

    """
    of_version = Version.of_version(version)
    wheel = load_embed_wheel(app_data, distribution, for_py_version, of_version)

    if version != Version.embed:
        # 2. check if we have upgraded embed
        if app_data.can_update:
            per = do_periodic_update
            wheel = periodic_update(distribution, of_version, for_py_version, wheel, search_dirs, app_data, per, env)

        # 3. acquire from extra search dir
        found_wheel = from_dir(distribution, of_version, for_py_version, search_dirs)
        if found_wheel is not None and (wheel is None or found_wheel.parsed_version > wheel.parsed_version):
            wheel = found_wheel
    return wheel


def load_embed_wheel(app_data: AppData, distribution: str, for_py_version: str, version: str | None) -> Wheel | None:
    """Return the bundled wheel of a distribution when it matches the version, extracted into the app data folder.

    :param app_data: the application data folder
    :param distribution: the distribution name
    :param for_py_version: the Python version the wheel must support
    :param version: the version to match, ``None`` for any version

    :returns: the wheel, ``None`` when no bundled wheel matches

    """
    wheel = get_embed_wheel(distribution, for_py_version)
    if wheel is not None:
        if version is None or wheel.has_version(version):
            with app_data.ensure_extracted(wheel.path) as wheel_path:
                wheel = Wheel(wheel_path)
        else:  # if version does not match ignore
            wheel = None
    return wheel


def from_dir(  # simplint: ignore[single-caller-helper, unexported-public-name]  # existing name
    distribution: str, version: str | None, for_py_version: str, directories: list[Path]
) -> Wheel | None:
    """Return the first wheel of the distribution found in the folders, or ``None`` when there is none.

    :param distribution: the name of the distribution
    :param version: the version to find, ``None`` for any
    :param for_py_version: the Python version the wheel must support
    :param directories: the folders to search, in order

    :returns: the wheel, or ``None``

    """  # simplint: ignore[function-docstring]  # existing docs
    for folder in directories:
        for wheel in discover_wheels(folder, distribution, version, for_py_version):
            return wheel
    return None


__all__ = [
    "from_bundle",
    "load_embed_wheel",
]
