"""Utilities for determining application-specific dirs.

Provides convenience functions (e.g. :func:`user_data_dir`, :func:`user_config_path`), a :data:`PlatformDirs` class that
auto-detects the current platform, and the :class:`~platformdirs.api.PlatformDirsABC` base class.

See <https://github.com/platformdirs/platformdirs> for details and usage.

PYTEST_DONT_REWRITE: Applications may import platformdirs before starting pytest.

"""

from __future__ import annotations

__lazy_modules__ = [
    f"{__spec__.parent}.api",  # ty: ignore[missing-union-attribute]  # imported modules have a spec
    f"{__spec__.parent}.version",  # ty: ignore[missing-union-attribute]  # imported modules have a spec
]

import os
import sys

from .api import PlatformDirsABC, RuntimeDirWarning
from .version import __version__
from .version import __version_tuple__ as __version_info__

TYPE_CHECKING = False
if TYPE_CHECKING:
    from pathlib import Path
    from typing import Literal


def _is_android_app() -> bool:
    # Android builds expose getandroidapilevel even when the environment is empty.
    if not hasattr(sys, "getandroidapilevel") and (
        os.getenv("ANDROID_DATA") != "/data" or os.getenv("ANDROID_ROOT") != "/system"
    ):
        return False
    if os.getenv("SHELL") or os.getenv("PREFIX"):
        return False
    from ._android import android_folder  # ruff:ignore[import-outside-top-level]  # Android-only lookup

    return android_folder() is not None


if not TYPE_CHECKING and _is_android_app():
    from .android import Android as PlatformDirs
elif sys.platform == "win32":
    from .windows import Windows as PlatformDirs
elif sys.platform == "darwin":
    from .macos import MacOS as PlatformDirs
elif sys.platform == "ios":
    from .ios import IOS as PlatformDirs  # ruff:ignore[constant-imported-as-non-constant]  # PEP 8 acronym
else:
    from .unix import Unix as PlatformDirs

AppDirs = PlatformDirs  #: Backwards compatibility with appdirs


def user_data_dir(  # ruff:ignore[too-many-arguments, too-many-positional-arguments]  # preserve released API
    appname: str | None = None,
    appauthor: str | Literal[False] | None = None,
    version: str | None = None,
    roaming: bool = False,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
    ensure_exists: bool = False,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
    use_site_for_root: bool = False,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
) -> str:
    """:param appname: See `appname <platformdirs.api.PlatformDirsABC.appname>`.
    :param appauthor: See `appauthor <platformdirs.api.PlatformDirsABC.appauthor>`.
    :param version: See `version <platformdirs.api.PlatformDirsABC.version>`.
    :param roaming: See `roaming <platformdirs.api.PlatformDirsABC.roaming>`.
    :param ensure_exists: See `ensure_exists <platformdirs.api.PlatformDirsABC.ensure_exists>`.
    :param use_site_for_root: See `use_site_for_root <platformdirs.api.PlatformDirsABC.use_site_for_root>`.

    :returns: data directory tied to the user

    """
    return PlatformDirs(
        appname=appname,
        appauthor=appauthor,
        version=version,
        roaming=roaming,
        ensure_exists=ensure_exists,
        use_site_for_root=use_site_for_root,
    ).user_data_dir


def site_data_dir(
    appname: str | None = None,
    appauthor: str | Literal[False] | None = None,
    version: str | None = None,
    multipath: bool = False,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
    ensure_exists: bool = False,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
) -> str:
    """:param appname: See `appname <platformdirs.api.PlatformDirsABC.appname>`.
    :param appauthor: See `appauthor <platformdirs.api.PlatformDirsABC.appauthor>`.
    :param version: See `version <platformdirs.api.PlatformDirsABC.version>`.
    :param multipath: See `multipath <platformdirs.api.PlatformDirsABC.multipath>`.
    :param ensure_exists: See `ensure_exists <platformdirs.api.PlatformDirsABC.ensure_exists>`.

    :returns: data directory shared by users

    """
    return PlatformDirs(
        appname=appname,
        appauthor=appauthor,
        version=version,
        multipath=multipath,
        ensure_exists=ensure_exists,
    ).site_data_dir


def user_config_dir(  # ruff:ignore[too-many-arguments, too-many-positional-arguments]  # preserve released API
    appname: str | None = None,
    appauthor: str | Literal[False] | None = None,
    version: str | None = None,
    roaming: bool = False,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
    ensure_exists: bool = False,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
    use_site_for_root: bool = False,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
) -> str:
    """:param appname: See `appname <platformdirs.api.PlatformDirsABC.appname>`.
    :param appauthor: See `appauthor <platformdirs.api.PlatformDirsABC.appauthor>`.
    :param version: See `version <platformdirs.api.PlatformDirsABC.version>`.
    :param roaming: See `roaming <platformdirs.api.PlatformDirsABC.roaming>`.
    :param ensure_exists: See `ensure_exists <platformdirs.api.PlatformDirsABC.ensure_exists>`.
    :param use_site_for_root: See `use_site_for_root <platformdirs.api.PlatformDirsABC.use_site_for_root>`.

    :returns: config directory tied to the user

    """
    return PlatformDirs(
        appname=appname,
        appauthor=appauthor,
        version=version,
        roaming=roaming,
        ensure_exists=ensure_exists,
        use_site_for_root=use_site_for_root,
    ).user_config_dir


def site_config_dir(
    appname: str | None = None,
    appauthor: str | Literal[False] | None = None,
    version: str | None = None,
    multipath: bool = False,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
    ensure_exists: bool = False,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
) -> str:
    """:param appname: See `appname <platformdirs.api.PlatformDirsABC.appname>`.
    :param appauthor: See `appauthor <platformdirs.api.PlatformDirsABC.appauthor>`.
    :param version: See `version <platformdirs.api.PlatformDirsABC.version>`.
    :param multipath: See `multipath <platformdirs.api.PlatformDirsABC.multipath>`.
    :param ensure_exists: See `ensure_exists <platformdirs.api.PlatformDirsABC.ensure_exists>`.

    :returns: config directory shared by users

    """
    return PlatformDirs(
        appname=appname,
        appauthor=appauthor,
        version=version,
        multipath=multipath,
        ensure_exists=ensure_exists,
    ).site_config_dir


def user_cache_dir(  # ruff:ignore[too-many-arguments, too-many-positional-arguments]  # preserve released API
    appname: str | None = None,
    appauthor: str | Literal[False] | None = None,
    version: str | None = None,
    opinion: bool = True,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
    ensure_exists: bool = False,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
    use_site_for_root: bool = False,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
) -> str:
    """:param appname: See `appname <platformdirs.api.PlatformDirsABC.appname>`.
    :param appauthor: See `appauthor <platformdirs.api.PlatformDirsABC.appauthor>`.
    :param version: See `version <platformdirs.api.PlatformDirsABC.version>`.
    :param opinion: See `opinion <platformdirs.api.PlatformDirsABC.opinion>`.
    :param ensure_exists: See `ensure_exists <platformdirs.api.PlatformDirsABC.ensure_exists>`.
    :param use_site_for_root: See `use_site_for_root <platformdirs.api.PlatformDirsABC.use_site_for_root>`.

    :returns: cache directory tied to the user

    """
    return PlatformDirs(
        appname=appname,
        appauthor=appauthor,
        version=version,
        opinion=opinion,
        ensure_exists=ensure_exists,
        use_site_for_root=use_site_for_root,
    ).user_cache_dir


def site_cache_dir(  # ruff:ignore[too-many-arguments]  # preserve released API
    appname: str | None = None,
    appauthor: str | Literal[False] | None = None,
    version: str | None = None,
    opinion: bool = True,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
    ensure_exists: bool = False,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
    *,
    multipath: bool = False,
) -> str:
    """:param appname: See `appname <platformdirs.api.PlatformDirsABC.appname>`.
    :param appauthor: See `appauthor <platformdirs.api.PlatformDirsABC.appauthor>`.
    :param version: See `version <platformdirs.api.PlatformDirsABC.version>`.
    :param opinion: See `opinion <platformdirs.api.PlatformDirsABC.opinion>`.
    :param ensure_exists: See `ensure_exists <platformdirs.api.PlatformDirsABC.ensure_exists>`.
    :param multipath: See `multipath <platformdirs.api.PlatformDirsABC.multipath>`.

    :returns: cache directory shared by users

    """
    return PlatformDirs(
        appname=appname,
        appauthor=appauthor,
        version=version,
        multipath=multipath,
        opinion=opinion,
        ensure_exists=ensure_exists,
    ).site_cache_dir


def user_state_dir(  # ruff:ignore[too-many-arguments, too-many-positional-arguments]  # preserve released API
    appname: str | None = None,
    appauthor: str | Literal[False] | None = None,
    version: str | None = None,
    roaming: bool = False,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
    ensure_exists: bool = False,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
    use_site_for_root: bool = False,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
) -> str:
    """:param appname: See `appname <platformdirs.api.PlatformDirsABC.appname>`.
    :param appauthor: See `appauthor <platformdirs.api.PlatformDirsABC.appauthor>`.
    :param version: See `version <platformdirs.api.PlatformDirsABC.version>`.
    :param roaming: See `roaming <platformdirs.api.PlatformDirsABC.roaming>`.
    :param ensure_exists: See `ensure_exists <platformdirs.api.PlatformDirsABC.ensure_exists>`.
    :param use_site_for_root: See `use_site_for_root <platformdirs.api.PlatformDirsABC.use_site_for_root>`.

    :returns: state directory tied to the user

    """
    return PlatformDirs(
        appname=appname,
        appauthor=appauthor,
        version=version,
        roaming=roaming,
        ensure_exists=ensure_exists,
        use_site_for_root=use_site_for_root,
    ).user_state_dir


def site_state_dir(
    appname: str | None = None,
    appauthor: str | Literal[False] | None = None,
    version: str | None = None,
    ensure_exists: bool = False,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
) -> str:
    """:param appname: See `appname <platformdirs.api.PlatformDirsABC.appname>`.
    :param appauthor: See `appauthor <platformdirs.api.PlatformDirsABC.appauthor>`.
    :param version: See `version <platformdirs.api.PlatformDirsABC.version>`.
    :param ensure_exists: See `ensure_exists <platformdirs.api.PlatformDirsABC.ensure_exists>`.

    :returns: state directory shared by users

    """
    return PlatformDirs(
        appname=appname,
        appauthor=appauthor,
        version=version,
        ensure_exists=ensure_exists,
    ).site_state_dir


def user_log_dir(  # ruff:ignore[too-many-arguments, too-many-positional-arguments]  # preserve released API
    appname: str | None = None,
    appauthor: str | Literal[False] | None = None,
    version: str | None = None,
    opinion: bool = True,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
    ensure_exists: bool = False,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
    use_site_for_root: bool = False,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
    *,
    roaming: bool = False,
) -> str:
    """:param appname: See `appname <platformdirs.api.PlatformDirsABC.appname>`.
    :param appauthor: See `appauthor <platformdirs.api.PlatformDirsABC.appauthor>`.
    :param version: See `version <platformdirs.api.PlatformDirsABC.version>`.
    :param opinion: See `opinion <platformdirs.api.PlatformDirsABC.opinion>`.
    :param ensure_exists: See `ensure_exists <platformdirs.api.PlatformDirsABC.ensure_exists>`.
    :param use_site_for_root: See `use_site_for_root <platformdirs.api.PlatformDirsABC.use_site_for_root>`.
    :param roaming: See `roaming <platformdirs.api.PlatformDirsABC.roaming>`.

    :returns: log directory tied to the user

    """
    return PlatformDirs(
        appname=appname,
        appauthor=appauthor,
        version=version,
        roaming=roaming,
        opinion=opinion,
        ensure_exists=ensure_exists,
        use_site_for_root=use_site_for_root,
    ).user_log_dir


def site_log_dir(
    appname: str | None = None,
    appauthor: str | Literal[False] | None = None,
    version: str | None = None,
    opinion: bool = True,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
    ensure_exists: bool = False,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
) -> str:
    """:param appname: See `appname <platformdirs.api.PlatformDirsABC.appname>`.
    :param appauthor: See `appauthor <platformdirs.api.PlatformDirsABC.appauthor>`.
    :param version: See `version <platformdirs.api.PlatformDirsABC.version>`.
    :param opinion: See `opinion <platformdirs.api.PlatformDirsABC.opinion>`.
    :param ensure_exists: See `ensure_exists <platformdirs.api.PlatformDirsABC.ensure_exists>`.

    :returns: log directory shared by users

    """
    return PlatformDirs(
        appname=appname,
        appauthor=appauthor,
        version=version,
        opinion=opinion,
        ensure_exists=ensure_exists,
    ).site_log_dir


def user_documents_dir(*, ensure_exists: bool = False, use_site_for_root: bool = False) -> str:
    """:param ensure_exists: See `ensure_exists <platformdirs.api.PlatformDirsABC.ensure_exists>`.
    :param use_site_for_root: See `use_site_for_root <platformdirs.api.PlatformDirsABC.use_site_for_root>`.

    :returns: documents directory tied to the user

    """
    return PlatformDirs(ensure_exists=ensure_exists, use_site_for_root=use_site_for_root).user_documents_dir


def user_downloads_dir(*, ensure_exists: bool = False, use_site_for_root: bool = False) -> str:
    """:param ensure_exists: See `ensure_exists <platformdirs.api.PlatformDirsABC.ensure_exists>`.
    :param use_site_for_root: See `use_site_for_root <platformdirs.api.PlatformDirsABC.use_site_for_root>`.

    :returns: downloads directory tied to the user

    """
    return PlatformDirs(ensure_exists=ensure_exists, use_site_for_root=use_site_for_root).user_downloads_dir


def user_pictures_dir(*, ensure_exists: bool = False, use_site_for_root: bool = False) -> str:
    """:param ensure_exists: See `ensure_exists <platformdirs.api.PlatformDirsABC.ensure_exists>`.
    :param use_site_for_root: See `use_site_for_root <platformdirs.api.PlatformDirsABC.use_site_for_root>`.

    :returns: pictures directory tied to the user

    """
    return PlatformDirs(ensure_exists=ensure_exists, use_site_for_root=use_site_for_root).user_pictures_dir


def user_videos_dir(*, ensure_exists: bool = False, use_site_for_root: bool = False) -> str:
    """:param ensure_exists: See `ensure_exists <platformdirs.api.PlatformDirsABC.ensure_exists>`.
    :param use_site_for_root: See `use_site_for_root <platformdirs.api.PlatformDirsABC.use_site_for_root>`.

    :returns: videos directory tied to the user

    """
    return PlatformDirs(ensure_exists=ensure_exists, use_site_for_root=use_site_for_root).user_videos_dir


def user_music_dir(*, ensure_exists: bool = False, use_site_for_root: bool = False) -> str:
    """:param ensure_exists: See `ensure_exists <platformdirs.api.PlatformDirsABC.ensure_exists>`.
    :param use_site_for_root: See `use_site_for_root <platformdirs.api.PlatformDirsABC.use_site_for_root>`.

    :returns: music directory tied to the user

    """
    return PlatformDirs(ensure_exists=ensure_exists, use_site_for_root=use_site_for_root).user_music_dir


def user_desktop_dir(*, ensure_exists: bool = False, use_site_for_root: bool = False) -> str:
    """:param ensure_exists: See `ensure_exists <platformdirs.api.PlatformDirsABC.ensure_exists>`.
    :param use_site_for_root: See `use_site_for_root <platformdirs.api.PlatformDirsABC.use_site_for_root>`.

    :returns: desktop directory tied to the user

    """
    return PlatformDirs(ensure_exists=ensure_exists, use_site_for_root=use_site_for_root).user_desktop_dir


def user_projects_dir(*, ensure_exists: bool = False, use_site_for_root: bool = False) -> str:
    """:param ensure_exists: See `ensure_exists <platformdirs.api.PlatformDirsABC.ensure_exists>`.
    :param use_site_for_root: See `use_site_for_root <platformdirs.api.PlatformDirsABC.use_site_for_root>`.

    :returns: projects directory tied to the user

    """
    return PlatformDirs(ensure_exists=ensure_exists, use_site_for_root=use_site_for_root).user_projects_dir


def user_publicshare_dir(*, ensure_exists: bool = False, use_site_for_root: bool = False) -> str:
    """:param ensure_exists: See `ensure_exists <platformdirs.api.PlatformDirsABC.ensure_exists>`.
    :param use_site_for_root: See `use_site_for_root <platformdirs.api.PlatformDirsABC.use_site_for_root>`.

    :returns: public share directory tied to the user

    """
    return PlatformDirs(ensure_exists=ensure_exists, use_site_for_root=use_site_for_root).user_publicshare_dir


def user_templates_dir(*, ensure_exists: bool = False, use_site_for_root: bool = False) -> str:
    """:param ensure_exists: See `ensure_exists <platformdirs.api.PlatformDirsABC.ensure_exists>`.
    :param use_site_for_root: See `use_site_for_root <platformdirs.api.PlatformDirsABC.use_site_for_root>`.

    :returns: templates directory tied to the user

    """
    return PlatformDirs(ensure_exists=ensure_exists, use_site_for_root=use_site_for_root).user_templates_dir


def user_fonts_dir(*, use_site_for_root: bool = False) -> str:
    """:param use_site_for_root: See `use_site_for_root <platformdirs.api.PlatformDirsABC.use_site_for_root>`.

    :returns: fonts directory tied to the user

    """
    return PlatformDirs(use_site_for_root=use_site_for_root).user_fonts_dir


def user_preference_dir(  # ruff:ignore[too-many-arguments]  # preserve released API
    appname: str | None = None,
    appauthor: str | Literal[False] | None = None,
    version: str | None = None,
    *,
    roaming: bool = False,
    ensure_exists: bool = False,
    use_site_for_root: bool = False,
) -> str:
    """:param appname: See `appname <platformdirs.api.PlatformDirsABC.appname>`.
    :param appauthor: See `appauthor <platformdirs.api.PlatformDirsABC.appauthor>`.
    :param version: See `version <platformdirs.api.PlatformDirsABC.version>`.
    :param roaming: See `roaming <platformdirs.api.PlatformDirsABC.roaming>`.
    :param ensure_exists: See `ensure_exists <platformdirs.api.PlatformDirsABC.ensure_exists>`.
    :param use_site_for_root: See `use_site_for_root <platformdirs.api.PlatformDirsABC.use_site_for_root>`.

    :returns: preference directory tied to the user

    """
    return PlatformDirs(
        appname=appname,
        appauthor=appauthor,
        version=version,
        roaming=roaming,
        ensure_exists=ensure_exists,
        use_site_for_root=use_site_for_root,
    ).user_preference_dir


def user_bin_dir(*, use_site_for_root: bool = False) -> str:
    """:param use_site_for_root: See `use_site_for_root <platformdirs.api.PlatformDirsABC.use_site_for_root>`.

    :returns: bin directory tied to the user

    """
    return PlatformDirs(use_site_for_root=use_site_for_root).user_bin_dir


def site_bin_dir() -> str:
    """:returns: bin directory shared by users"""
    return PlatformDirs().site_bin_dir


def user_applications_dir(
    appname: str | None = None,
    appauthor: str | Literal[False] | None = None,
    version: str | None = None,
    *,
    ensure_exists: bool = False,
    use_site_for_root: bool = False,
) -> str:
    """:param appname: See `appname <platformdirs.api.PlatformDirsABC.appname>`.
    :param appauthor: See `appauthor <platformdirs.api.PlatformDirsABC.appauthor>`.
    :param version: See `version <platformdirs.api.PlatformDirsABC.version>`.
    :param ensure_exists: See `ensure_exists <platformdirs.api.PlatformDirsABC.ensure_exists>`.
    :param use_site_for_root: See `use_site_for_root <platformdirs.api.PlatformDirsABC.use_site_for_root>`.

    :returns: applications directory tied to the user

    """
    return PlatformDirs(
        appname=appname,
        appauthor=appauthor,
        version=version,
        ensure_exists=ensure_exists,
        use_site_for_root=use_site_for_root,
    ).user_applications_dir


def site_applications_dir(
    multipath: bool = False,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
    ensure_exists: bool = False,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
    *,
    appname: str | None = None,
    appauthor: str | Literal[False] | None = None,
    version: str | None = None,
) -> str:
    """:param multipath: See `multipath <platformdirs.api.PlatformDirsABC.multipath>`.
    :param ensure_exists: See `ensure_exists <platformdirs.api.PlatformDirsABC.ensure_exists>`.
    :param appname: See `appname <platformdirs.api.PlatformDirsABC.appname>`.
    :param appauthor: See `appauthor <platformdirs.api.PlatformDirsABC.appauthor>`.
    :param version: See `version <platformdirs.api.PlatformDirsABC.version>`.

    :returns: applications directory shared by users

    """
    return PlatformDirs(
        appname=appname,
        appauthor=appauthor,
        version=version,
        multipath=multipath,
        ensure_exists=ensure_exists,
    ).site_applications_dir


def user_runtime_dir(  # ruff:ignore[too-many-arguments, too-many-positional-arguments]  # preserve released API
    appname: str | None = None,
    appauthor: str | Literal[False] | None = None,
    version: str | None = None,
    opinion: bool = True,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
    ensure_exists: bool = False,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
    use_site_for_root: bool = False,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
) -> str:
    """:param appname: See `appname <platformdirs.api.PlatformDirsABC.appname>`.
    :param appauthor: See `appauthor <platformdirs.api.PlatformDirsABC.appauthor>`.
    :param version: See `version <platformdirs.api.PlatformDirsABC.version>`.
    :param opinion: See `opinion <platformdirs.api.PlatformDirsABC.opinion>`.
    :param ensure_exists: See `ensure_exists <platformdirs.api.PlatformDirsABC.ensure_exists>`.
    :param use_site_for_root: See `use_site_for_root <platformdirs.api.PlatformDirsABC.use_site_for_root>`.

    :returns: runtime directory tied to the user

    """
    return PlatformDirs(
        appname=appname,
        appauthor=appauthor,
        version=version,
        opinion=opinion,
        ensure_exists=ensure_exists,
        use_site_for_root=use_site_for_root,
    ).user_runtime_dir


def site_runtime_dir(
    appname: str | None = None,
    appauthor: str | Literal[False] | None = None,
    version: str | None = None,
    opinion: bool = True,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
    ensure_exists: bool = False,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
) -> str:
    """:param appname: See `appname <platformdirs.api.PlatformDirsABC.appname>`.
    :param appauthor: See `appauthor <platformdirs.api.PlatformDirsABC.appauthor>`.
    :param version: See `version <platformdirs.api.PlatformDirsABC.version>`.
    :param opinion: See `opinion <platformdirs.api.PlatformDirsABC.opinion>`.
    :param ensure_exists: See `ensure_exists <platformdirs.api.PlatformDirsABC.ensure_exists>`.

    :returns: runtime directory shared by users

    """
    return PlatformDirs(
        appname=appname,
        appauthor=appauthor,
        version=version,
        opinion=opinion,
        ensure_exists=ensure_exists,
    ).site_runtime_dir


def user_data_path(  # ruff:ignore[too-many-arguments, too-many-positional-arguments]  # preserve released API
    appname: str | None = None,
    appauthor: str | Literal[False] | None = None,
    version: str | None = None,
    roaming: bool = False,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
    ensure_exists: bool = False,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
    use_site_for_root: bool = False,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
) -> Path:
    """:param appname: See `appname <platformdirs.api.PlatformDirsABC.appname>`.
    :param appauthor: See `appauthor <platformdirs.api.PlatformDirsABC.appauthor>`.
    :param version: See `version <platformdirs.api.PlatformDirsABC.version>`.
    :param roaming: See `roaming <platformdirs.api.PlatformDirsABC.roaming>`.
    :param ensure_exists: See `ensure_exists <platformdirs.api.PlatformDirsABC.ensure_exists>`.
    :param use_site_for_root: See `use_site_for_root <platformdirs.api.PlatformDirsABC.use_site_for_root>`.

    :returns: data path tied to the user

    """
    return PlatformDirs(
        appname=appname,
        appauthor=appauthor,
        version=version,
        roaming=roaming,
        ensure_exists=ensure_exists,
        use_site_for_root=use_site_for_root,
    ).user_data_path


def site_data_path(
    appname: str | None = None,
    appauthor: str | Literal[False] | None = None,
    version: str | None = None,
    multipath: bool = False,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
    ensure_exists: bool = False,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
) -> Path:
    """:param appname: See `appname <platformdirs.api.PlatformDirsABC.appname>`.
    :param appauthor: See `appauthor <platformdirs.api.PlatformDirsABC.appauthor>`.
    :param version: See `version <platformdirs.api.PlatformDirsABC.version>`.
    :param multipath: See `multipath <platformdirs.api.PlatformDirsABC.multipath>`.
    :param ensure_exists: See `ensure_exists <platformdirs.api.PlatformDirsABC.ensure_exists>`.

    :returns: data path shared by users

    """
    return PlatformDirs(
        appname=appname,
        appauthor=appauthor,
        version=version,
        multipath=multipath,
        ensure_exists=ensure_exists,
    ).site_data_path


def user_config_path(  # ruff:ignore[too-many-arguments, too-many-positional-arguments]  # preserve released API
    appname: str | None = None,
    appauthor: str | Literal[False] | None = None,
    version: str | None = None,
    roaming: bool = False,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
    ensure_exists: bool = False,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
    use_site_for_root: bool = False,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
) -> Path:
    """:param appname: See `appname <platformdirs.api.PlatformDirsABC.appname>`.
    :param appauthor: See `appauthor <platformdirs.api.PlatformDirsABC.appauthor>`.
    :param version: See `version <platformdirs.api.PlatformDirsABC.version>`.
    :param roaming: See `roaming <platformdirs.api.PlatformDirsABC.roaming>`.
    :param ensure_exists: See `ensure_exists <platformdirs.api.PlatformDirsABC.ensure_exists>`.
    :param use_site_for_root: See `use_site_for_root <platformdirs.api.PlatformDirsABC.use_site_for_root>`.

    :returns: config path tied to the user

    """
    return PlatformDirs(
        appname=appname,
        appauthor=appauthor,
        version=version,
        roaming=roaming,
        ensure_exists=ensure_exists,
        use_site_for_root=use_site_for_root,
    ).user_config_path


def site_config_path(
    appname: str | None = None,
    appauthor: str | Literal[False] | None = None,
    version: str | None = None,
    multipath: bool = False,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
    ensure_exists: bool = False,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
) -> Path:
    """:param appname: See `appname <platformdirs.api.PlatformDirsABC.appname>`.
    :param appauthor: See `appauthor <platformdirs.api.PlatformDirsABC.appauthor>`.
    :param version: See `version <platformdirs.api.PlatformDirsABC.version>`.
    :param multipath: See `multipath <platformdirs.api.PlatformDirsABC.multipath>`.
    :param ensure_exists: See `ensure_exists <platformdirs.api.PlatformDirsABC.ensure_exists>`.

    :returns: config path shared by users

    """
    return PlatformDirs(
        appname=appname,
        appauthor=appauthor,
        version=version,
        multipath=multipath,
        ensure_exists=ensure_exists,
    ).site_config_path


def site_cache_path(  # ruff:ignore[too-many-arguments]  # preserve released API
    appname: str | None = None,
    appauthor: str | Literal[False] | None = None,
    version: str | None = None,
    opinion: bool = True,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
    ensure_exists: bool = False,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
    *,
    multipath: bool = False,
) -> Path:
    """:param appname: See `appname <platformdirs.api.PlatformDirsABC.appname>`.
    :param appauthor: See `appauthor <platformdirs.api.PlatformDirsABC.appauthor>`.
    :param version: See `version <platformdirs.api.PlatformDirsABC.version>`.
    :param opinion: See `opinion <platformdirs.api.PlatformDirsABC.opinion>`.
    :param ensure_exists: See `ensure_exists <platformdirs.api.PlatformDirsABC.ensure_exists>`.
    :param multipath: See `multipath <platformdirs.api.PlatformDirsABC.multipath>`.

    :returns: cache path shared by users

    """
    return PlatformDirs(
        appname=appname,
        appauthor=appauthor,
        version=version,
        multipath=multipath,
        opinion=opinion,
        ensure_exists=ensure_exists,
    ).site_cache_path


def user_cache_path(  # ruff:ignore[too-many-arguments, too-many-positional-arguments]  # preserve released API
    appname: str | None = None,
    appauthor: str | Literal[False] | None = None,
    version: str | None = None,
    opinion: bool = True,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
    ensure_exists: bool = False,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
    use_site_for_root: bool = False,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
) -> Path:
    """:param appname: See `appname <platformdirs.api.PlatformDirsABC.appname>`.
    :param appauthor: See `appauthor <platformdirs.api.PlatformDirsABC.appauthor>`.
    :param version: See `version <platformdirs.api.PlatformDirsABC.version>`.
    :param opinion: See `opinion <platformdirs.api.PlatformDirsABC.opinion>`.
    :param ensure_exists: See `ensure_exists <platformdirs.api.PlatformDirsABC.ensure_exists>`.
    :param use_site_for_root: See `use_site_for_root <platformdirs.api.PlatformDirsABC.use_site_for_root>`.

    :returns: cache path tied to the user

    """
    return PlatformDirs(
        appname=appname,
        appauthor=appauthor,
        version=version,
        opinion=opinion,
        ensure_exists=ensure_exists,
        use_site_for_root=use_site_for_root,
    ).user_cache_path


def user_state_path(  # ruff:ignore[too-many-arguments, too-many-positional-arguments]  # preserve released API
    appname: str | None = None,
    appauthor: str | Literal[False] | None = None,
    version: str | None = None,
    roaming: bool = False,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
    ensure_exists: bool = False,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
    use_site_for_root: bool = False,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
) -> Path:
    """:param appname: See `appname <platformdirs.api.PlatformDirsABC.appname>`.
    :param appauthor: See `appauthor <platformdirs.api.PlatformDirsABC.appauthor>`.
    :param version: See `version <platformdirs.api.PlatformDirsABC.version>`.
    :param roaming: See `roaming <platformdirs.api.PlatformDirsABC.roaming>`.
    :param ensure_exists: See `ensure_exists <platformdirs.api.PlatformDirsABC.ensure_exists>`.
    :param use_site_for_root: See `use_site_for_root <platformdirs.api.PlatformDirsABC.use_site_for_root>`.

    :returns: state path tied to the user

    """
    return PlatformDirs(
        appname=appname,
        appauthor=appauthor,
        version=version,
        roaming=roaming,
        ensure_exists=ensure_exists,
        use_site_for_root=use_site_for_root,
    ).user_state_path


def site_state_path(
    appname: str | None = None,
    appauthor: str | Literal[False] | None = None,
    version: str | None = None,
    ensure_exists: bool = False,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
) -> Path:
    """:param appname: See `appname <platformdirs.api.PlatformDirsABC.appname>`.
    :param appauthor: See `appauthor <platformdirs.api.PlatformDirsABC.appauthor>`.
    :param version: See `version <platformdirs.api.PlatformDirsABC.version>`.
    :param ensure_exists: See `ensure_exists <platformdirs.api.PlatformDirsABC.ensure_exists>`.

    :returns: state path shared by users

    """
    return PlatformDirs(
        appname=appname,
        appauthor=appauthor,
        version=version,
        ensure_exists=ensure_exists,
    ).site_state_path


def user_log_path(  # ruff:ignore[too-many-arguments, too-many-positional-arguments]  # preserve released API
    appname: str | None = None,
    appauthor: str | Literal[False] | None = None,
    version: str | None = None,
    opinion: bool = True,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
    ensure_exists: bool = False,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
    use_site_for_root: bool = False,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
    *,
    roaming: bool = False,
) -> Path:
    """:param appname: See `appname <platformdirs.api.PlatformDirsABC.appname>`.
    :param appauthor: See `appauthor <platformdirs.api.PlatformDirsABC.appauthor>`.
    :param version: See `version <platformdirs.api.PlatformDirsABC.version>`.
    :param opinion: See `opinion <platformdirs.api.PlatformDirsABC.opinion>`.
    :param ensure_exists: See `ensure_exists <platformdirs.api.PlatformDirsABC.ensure_exists>`.
    :param use_site_for_root: See `use_site_for_root <platformdirs.api.PlatformDirsABC.use_site_for_root>`.
    :param roaming: See `roaming <platformdirs.api.PlatformDirsABC.roaming>`.

    :returns: log path tied to the user

    """
    return PlatformDirs(
        appname=appname,
        appauthor=appauthor,
        version=version,
        roaming=roaming,
        opinion=opinion,
        ensure_exists=ensure_exists,
        use_site_for_root=use_site_for_root,
    ).user_log_path


def site_log_path(
    appname: str | None = None,
    appauthor: str | Literal[False] | None = None,
    version: str | None = None,
    opinion: bool = True,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
    ensure_exists: bool = False,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
) -> Path:
    """:param appname: See `appname <platformdirs.api.PlatformDirsABC.appname>`.
    :param appauthor: See `appauthor <platformdirs.api.PlatformDirsABC.appauthor>`.
    :param version: See `version <platformdirs.api.PlatformDirsABC.version>`.
    :param opinion: See `opinion <platformdirs.api.PlatformDirsABC.opinion>`.
    :param ensure_exists: See `ensure_exists <platformdirs.api.PlatformDirsABC.ensure_exists>`.

    :returns: log path shared by users

    """
    return PlatformDirs(
        appname=appname,
        appauthor=appauthor,
        version=version,
        opinion=opinion,
        ensure_exists=ensure_exists,
    ).site_log_path


def user_documents_path(*, ensure_exists: bool = False, use_site_for_root: bool = False) -> Path:
    """:param ensure_exists: See `ensure_exists <platformdirs.api.PlatformDirsABC.ensure_exists>`.
    :param use_site_for_root: See `use_site_for_root <platformdirs.api.PlatformDirsABC.use_site_for_root>`.

    :returns: documents path tied to the user

    """
    return PlatformDirs(ensure_exists=ensure_exists, use_site_for_root=use_site_for_root).user_documents_path


def user_downloads_path(*, ensure_exists: bool = False, use_site_for_root: bool = False) -> Path:
    """:param ensure_exists: See `ensure_exists <platformdirs.api.PlatformDirsABC.ensure_exists>`.
    :param use_site_for_root: See `use_site_for_root <platformdirs.api.PlatformDirsABC.use_site_for_root>`.

    :returns: downloads path tied to the user

    """
    return PlatformDirs(ensure_exists=ensure_exists, use_site_for_root=use_site_for_root).user_downloads_path


def user_pictures_path(*, ensure_exists: bool = False, use_site_for_root: bool = False) -> Path:
    """:param ensure_exists: See `ensure_exists <platformdirs.api.PlatformDirsABC.ensure_exists>`.
    :param use_site_for_root: See `use_site_for_root <platformdirs.api.PlatformDirsABC.use_site_for_root>`.

    :returns: pictures path tied to the user

    """
    return PlatformDirs(ensure_exists=ensure_exists, use_site_for_root=use_site_for_root).user_pictures_path


def user_videos_path(*, ensure_exists: bool = False, use_site_for_root: bool = False) -> Path:
    """:param ensure_exists: See `ensure_exists <platformdirs.api.PlatformDirsABC.ensure_exists>`.
    :param use_site_for_root: See `use_site_for_root <platformdirs.api.PlatformDirsABC.use_site_for_root>`.

    :returns: videos path tied to the user

    """
    return PlatformDirs(ensure_exists=ensure_exists, use_site_for_root=use_site_for_root).user_videos_path


def user_music_path(*, ensure_exists: bool = False, use_site_for_root: bool = False) -> Path:
    """:param ensure_exists: See `ensure_exists <platformdirs.api.PlatformDirsABC.ensure_exists>`.
    :param use_site_for_root: See `use_site_for_root <platformdirs.api.PlatformDirsABC.use_site_for_root>`.

    :returns: music path tied to the user

    """
    return PlatformDirs(ensure_exists=ensure_exists, use_site_for_root=use_site_for_root).user_music_path


def user_desktop_path(*, ensure_exists: bool = False, use_site_for_root: bool = False) -> Path:
    """:param ensure_exists: See `ensure_exists <platformdirs.api.PlatformDirsABC.ensure_exists>`.
    :param use_site_for_root: See `use_site_for_root <platformdirs.api.PlatformDirsABC.use_site_for_root>`.

    :returns: desktop path tied to the user

    """
    return PlatformDirs(ensure_exists=ensure_exists, use_site_for_root=use_site_for_root).user_desktop_path


def user_projects_path(*, ensure_exists: bool = False, use_site_for_root: bool = False) -> Path:
    """:param ensure_exists: See `ensure_exists <platformdirs.api.PlatformDirsABC.ensure_exists>`.
    :param use_site_for_root: See `use_site_for_root <platformdirs.api.PlatformDirsABC.use_site_for_root>`.

    :returns: projects path tied to the user

    """
    return PlatformDirs(ensure_exists=ensure_exists, use_site_for_root=use_site_for_root).user_projects_path


def user_publicshare_path(*, ensure_exists: bool = False, use_site_for_root: bool = False) -> Path:
    """:param ensure_exists: See `ensure_exists <platformdirs.api.PlatformDirsABC.ensure_exists>`.
    :param use_site_for_root: See `use_site_for_root <platformdirs.api.PlatformDirsABC.use_site_for_root>`.

    :returns: public share path tied to the user

    """
    return PlatformDirs(ensure_exists=ensure_exists, use_site_for_root=use_site_for_root).user_publicshare_path


def user_templates_path(*, ensure_exists: bool = False, use_site_for_root: bool = False) -> Path:
    """:param ensure_exists: See `ensure_exists <platformdirs.api.PlatformDirsABC.ensure_exists>`.
    :param use_site_for_root: See `use_site_for_root <platformdirs.api.PlatformDirsABC.use_site_for_root>`.

    :returns: templates path tied to the user

    """
    return PlatformDirs(ensure_exists=ensure_exists, use_site_for_root=use_site_for_root).user_templates_path


def user_fonts_path(*, use_site_for_root: bool = False) -> Path:
    """:param use_site_for_root: See `use_site_for_root <platformdirs.api.PlatformDirsABC.use_site_for_root>`.

    :returns: fonts path tied to the user

    """
    return PlatformDirs(use_site_for_root=use_site_for_root).user_fonts_path


def user_preference_path(  # ruff:ignore[too-many-arguments]  # preserve released API
    appname: str | None = None,
    appauthor: str | Literal[False] | None = None,
    version: str | None = None,
    *,
    roaming: bool = False,
    ensure_exists: bool = False,
    use_site_for_root: bool = False,
) -> Path:
    """:param appname: See `appname <platformdirs.api.PlatformDirsABC.appname>`.
    :param appauthor: See `appauthor <platformdirs.api.PlatformDirsABC.appauthor>`.
    :param version: See `version <platformdirs.api.PlatformDirsABC.version>`.
    :param roaming: See `roaming <platformdirs.api.PlatformDirsABC.roaming>`.
    :param ensure_exists: See `ensure_exists <platformdirs.api.PlatformDirsABC.ensure_exists>`.
    :param use_site_for_root: See `use_site_for_root <platformdirs.api.PlatformDirsABC.use_site_for_root>`.

    :returns: preference path tied to the user

    """
    return PlatformDirs(
        appname=appname,
        appauthor=appauthor,
        version=version,
        roaming=roaming,
        ensure_exists=ensure_exists,
        use_site_for_root=use_site_for_root,
    ).user_preference_path


def user_bin_path(*, use_site_for_root: bool = False) -> Path:
    """:param use_site_for_root: See `use_site_for_root <platformdirs.api.PlatformDirsABC.use_site_for_root>`.

    :returns: bin path tied to the user

    """
    return PlatformDirs(use_site_for_root=use_site_for_root).user_bin_path


def site_bin_path() -> Path:
    """:returns: bin path shared by users"""
    return PlatformDirs().site_bin_path


def user_applications_path(
    appname: str | None = None,
    appauthor: str | Literal[False] | None = None,
    version: str | None = None,
    *,
    ensure_exists: bool = False,
    use_site_for_root: bool = False,
) -> Path:
    """:param appname: See `appname <platformdirs.api.PlatformDirsABC.appname>`.
    :param appauthor: See `appauthor <platformdirs.api.PlatformDirsABC.appauthor>`.
    :param version: See `version <platformdirs.api.PlatformDirsABC.version>`.
    :param ensure_exists: See `ensure_exists <platformdirs.api.PlatformDirsABC.ensure_exists>`.
    :param use_site_for_root: See `use_site_for_root <platformdirs.api.PlatformDirsABC.use_site_for_root>`.

    :returns: applications path tied to the user

    """
    return PlatformDirs(
        appname=appname,
        appauthor=appauthor,
        version=version,
        ensure_exists=ensure_exists,
        use_site_for_root=use_site_for_root,
    ).user_applications_path


def site_applications_path(
    multipath: bool = False,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
    ensure_exists: bool = False,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
    *,
    appname: str | None = None,
    appauthor: str | Literal[False] | None = None,
    version: str | None = None,
) -> Path:
    """:param multipath: See `multipath <platformdirs.api.PlatformDirsABC.multipath>`.
    :param ensure_exists: See `ensure_exists <platformdirs.api.PlatformDirsABC.ensure_exists>`.
    :param appname: See `appname <platformdirs.api.PlatformDirsABC.appname>`.
    :param appauthor: See `appauthor <platformdirs.api.PlatformDirsABC.appauthor>`.
    :param version: See `version <platformdirs.api.PlatformDirsABC.version>`.

    :returns: applications path shared by users

    """
    return PlatformDirs(
        appname=appname,
        appauthor=appauthor,
        version=version,
        multipath=multipath,
        ensure_exists=ensure_exists,
    ).site_applications_path


def user_runtime_path(  # ruff:ignore[too-many-arguments, too-many-positional-arguments]  # preserve released API
    appname: str | None = None,
    appauthor: str | Literal[False] | None = None,
    version: str | None = None,
    opinion: bool = True,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
    ensure_exists: bool = False,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
    use_site_for_root: bool = False,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
) -> Path:
    """:param appname: See `appname <platformdirs.api.PlatformDirsABC.appname>`.
    :param appauthor: See `appauthor <platformdirs.api.PlatformDirsABC.appauthor>`.
    :param version: See `version <platformdirs.api.PlatformDirsABC.version>`.
    :param opinion: See `opinion <platformdirs.api.PlatformDirsABC.opinion>`.
    :param ensure_exists: See `ensure_exists <platformdirs.api.PlatformDirsABC.ensure_exists>`.
    :param use_site_for_root: See `use_site_for_root <platformdirs.api.PlatformDirsABC.use_site_for_root>`.

    :returns: runtime path tied to the user

    """
    return PlatformDirs(
        appname=appname,
        appauthor=appauthor,
        version=version,
        opinion=opinion,
        ensure_exists=ensure_exists,
        use_site_for_root=use_site_for_root,
    ).user_runtime_path


def site_runtime_path(
    appname: str | None = None,
    appauthor: str | Literal[False] | None = None,
    version: str | None = None,
    opinion: bool = True,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
    ensure_exists: bool = False,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
) -> Path:
    """:param appname: See `appname <platformdirs.api.PlatformDirsABC.appname>`.
    :param appauthor: See `appauthor <platformdirs.api.PlatformDirsABC.appauthor>`.
    :param version: See `version <platformdirs.api.PlatformDirsABC.version>`.
    :param opinion: See `opinion <platformdirs.api.PlatformDirsABC.opinion>`.
    :param ensure_exists: See `ensure_exists <platformdirs.api.PlatformDirsABC.ensure_exists>`.

    :returns: runtime path shared by users

    """
    return PlatformDirs(
        appname=appname,
        appauthor=appauthor,
        version=version,
        opinion=opinion,
        ensure_exists=ensure_exists,
    ).site_runtime_path


__all__ = [
    "AppDirs",
    "PlatformDirs",
    "PlatformDirsABC",
    "RuntimeDirWarning",
    "__version__",
    "__version_info__",
    "site_applications_dir",
    "site_applications_path",
    "site_bin_dir",
    "site_bin_path",
    "site_cache_dir",
    "site_cache_path",
    "site_config_dir",
    "site_config_path",
    "site_data_dir",
    "site_data_path",
    "site_log_dir",
    "site_log_path",
    "site_runtime_dir",
    "site_runtime_path",
    "site_state_dir",
    "site_state_path",
    "user_applications_dir",
    "user_applications_path",
    "user_bin_dir",
    "user_bin_path",
    "user_cache_dir",
    "user_cache_path",
    "user_config_dir",
    "user_config_path",
    "user_data_dir",
    "user_data_path",
    "user_desktop_dir",
    "user_desktop_path",
    "user_documents_dir",
    "user_documents_path",
    "user_downloads_dir",
    "user_downloads_path",
    "user_fonts_dir",
    "user_fonts_path",
    "user_log_dir",
    "user_log_path",
    "user_music_dir",
    "user_music_path",
    "user_pictures_dir",
    "user_pictures_path",
    "user_preference_dir",
    "user_preference_path",
    "user_projects_dir",
    "user_projects_path",
    "user_publicshare_dir",
    "user_publicshare_path",
    "user_runtime_dir",
    "user_runtime_path",
    "user_state_dir",
    "user_state_path",
    "user_templates_dir",
    "user_templates_path",
    "user_videos_dir",
    "user_videos_path",
]
