"""macOS."""

from __future__ import annotations

__lazy_modules__ = [
    "contextlib",
    "pathlib",
    f"{__spec__.parent}._runtime",  # ty: ignore[missing-union-attribute]  # imported modules have a spec
]

import os
import re
import stat
import sys
from contextlib import suppress
from pathlib import Path

from ._runtime import runtime_base_problem
from ._xdg import XDGMixin, expand_user, xdg_dir
from .api import PlatformDirsABC

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator
    from typing import Final, NoReturn

if sys.platform == "win32":

    def geteuid() -> NoReturn:
        msg = "should only be used on macOS"
        raise RuntimeError(msg)

else:
    from os import geteuid


class _MacOSDefaults(PlatformDirsABC):  # ruff:ignore[too-many-public-methods]  # full directory API
    """Default platform directories for macOS without XDG environment variable overrides.

    Follows the guidance from `Apple's File System Programming Guide
    <https://developer.apple.com/library/archive/documentation/FileManagement/Conceptual/FileSystemProgrammingGuide/MacOSXDirectories/MacOSXDirectories.html>`_.
    The XDG env var handling is in :class:`~platformdirs._xdg.XDGMixin`.

    """

    @property
    def user_data_dir(self) -> str:
        """Data directory tied to the user, e.g. ``~/Library/Application Support/$appname/$version``."""
        return self._base_user_app_support_dir()

    def _base_user_app_support_dir(self) -> str:
        return self._append_app_name_and_version(expand_user("~/Library/Application Support"), private=True)

    @property
    def _site_data_dirs(self) -> list[str]:
        return self._base_site_dirs()

    def _base_site_dirs(self) -> list[str]:
        path_list = [self._join_app_name_and_version(f"{prefix}/share")] if (prefix := _homebrew_prefix()) else []
        path_list.append(self._join_app_name_and_version("/Library/Application Support"))
        return path_list

    @property
    def user_config_dir(self) -> str:
        """Config directory tied to the user, same as `user_data_dir`."""
        return self._base_user_app_support_dir()

    @property
    def _site_config_dirs(self) -> list[str]:
        return self._base_site_dirs()

    @property
    def user_cache_dir(self) -> str:
        """Cache directory tied to the user, e.g. ``~/Library/Caches/$appname/$version``."""
        return self._append_app_name_and_version(expand_user("~/Library/Caches"), private=True)

    @property
    def site_cache_dir(self) -> str:
        """Cache directory shared by users, e.g. ``/Library/Caches/$appname/$version``.

        If we're using a Python binary managed by `Homebrew <https://brew.sh>`_, the directory will be under the
        Homebrew prefix, e.g. ``$homebrew_prefix/var/cache/$appname/$version``. If
        `multipath <platformdirs.api.PlatformDirsABC.multipath>` is enabled, and we're in Homebrew, the response is a
        multi-path string separated by ":", e.g.
        ``$homebrew_prefix/var/cache/$appname/$version:/Library/Caches/$appname/$version``.


        :raises PermissionError: under `ensure_exists <platformdirs.api.PlatformDirsABC.ensure_exists>`, if
            ``/Library/Caches/$appname`` is a symlink, not a directory or owned by a user other than root and the
            current one.

        """
        return self._select_site_dirs(self._site_cache_dirs)

    @property
    def _site_cache_dirs(self) -> list[str]:
        path_list = [self._join_app_name_and_version(f"{prefix}/var/cache")] if (prefix := _homebrew_prefix()) else []
        path_list.append(self._join_app_name_and_version(_SITE_CACHE))
        return path_list

    @property
    def user_state_dir(self) -> str:
        """State directory tied to the user, same as `user_data_dir` without ``$XDG_DATA_HOME``.

        E.g. ``~/Library/Application Support/$appname/$version``.

        """
        return self._base_user_app_support_dir()

    @property
    def site_state_dir(self) -> str:
        """State directory shared by users, the first entry of `site_data_dir` without ``$XDG_DATA_DIRS``.

        Ignores `multipath <platformdirs.api.PlatformDirsABC.multipath>`.

        """
        path = self._base_site_dirs()[0]
        self._optionally_create_directory(path, private=False, site=True)
        return path

    # Default platform directories for macOS without XDG environment variable overrides.
    #
    # Follows the guidance from `Apple's File System Programming Guide
    # <https://developer.apple.com/library/archive/documentation/FileManagement/Conceptual/FileSystemProgrammingGuide/MacOSXDirectories/MacOSXDirectories.html>`_.
    # The XDG env var handling is in :class:`~platformdirs._xdg.XDGMixin`.
    def _optionally_create_directory(
        self, path: str, *, private: bool, site: bool = False, strict: bool = False
    ) -> None:
        if self.ensure_exists and (shared := Path(_SITE_CACHE)) in (target := Path(path)).parents:
            # Every user can write to /Library/Caches, so another one may have created this entry first.
            entry = shared / target.relative_to(shared).parts[0]
            with suppress(FileExistsError):
                super()._optionally_create_directory(str(entry), private=private, site=site, strict=strict)
            if problem := self._shared_entry_problem(entry):
                msg = f"site cache directory {problem}"
                raise PermissionError(msg)
            if target == entry:
                return
        super()._optionally_create_directory(path, private=private, site=site, strict=strict)

    @staticmethod
    def _shared_entry_problem(path: Path) -> str | None:
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode):
            return f"{path} is a symlink"
        if not stat.S_ISDIR(info.st_mode):
            return f"{path} is not a directory"
        if info.st_uid != 0 and info.st_uid != (euid := geteuid()):
            return f"{path} is owned by uid {info.st_uid}, not root or {euid}"
        return None

    @property
    def user_log_dir(self) -> str:
        """Log directory tied to the user, e.g. ``~/Library/Logs/$appname/$version``."""
        return self._append_app_name_and_version(expand_user("~/Library/Logs"), private=True)

    @property
    def site_log_dir(self) -> str:
        """Log directory shared by users, e.g. ``/Library/Logs/$appname/$version``."""
        return self._append_app_name_and_version("/Library/Logs", private=False)

    @property
    def user_documents_dir(self) -> str:
        """Documents directory tied to the user, e.g. ``~/Documents``."""
        return expand_user("~/Documents")

    @property
    def user_downloads_dir(self) -> str:
        """Downloads directory tied to the user, e.g. ``~/Downloads``."""
        return expand_user("~/Downloads")

    @property
    def user_pictures_dir(self) -> str:
        """Pictures directory tied to the user, e.g. ``~/Pictures``."""
        return expand_user("~/Pictures")

    @property
    def user_videos_dir(self) -> str:
        """Videos directory tied to the user, e.g. ``~/Movies``."""
        return expand_user("~/Movies")

    @property
    def user_music_dir(self) -> str:
        """Music directory tied to the user, e.g. ``~/Music``."""
        return expand_user("~/Music")

    @property
    def user_desktop_dir(self) -> str:
        """Desktop directory tied to the user, e.g. ``~/Desktop``."""
        return expand_user("~/Desktop")

    @property
    def user_projects_dir(self) -> str:
        """Projects directory tied to the user, e.g. ``~/Projects``."""
        return expand_user("~/Projects")

    @property
    def user_publicshare_dir(self) -> str:
        """Public share directory tied to the user, e.g. ``~/Public``."""
        return expand_user("~/Public")

    @property
    def user_templates_dir(self) -> str:
        """Templates directory tied to the user, e.g. ``~/Templates``."""
        return expand_user("~/Templates")

    @property
    def user_fonts_dir(self) -> str:
        """Fonts directory tied to the user, e.g. ``~/Library/Fonts``."""
        return expand_user("~/Library/Fonts")

    @property
    def user_preference_dir(self) -> str:
        """Preference directory tied to the user, e.g. ``~/Library/Preferences/AppName``."""
        return self._append_app_name_and_version(expand_user("~/Library/Preferences"), private=True)

    @property
    def user_bin_dir(self) -> str:
        """Bin directory tied to the user, e.g. ``~/.local/bin``."""
        return expand_user("~/.local/bin")

    @property
    def site_bin_dir(self) -> str:
        """Bin directory shared by users, e.g. ``/usr/local/bin``."""
        return "/usr/local/bin"

    @property
    def user_applications_dir(self) -> str:
        """Applications directory tied to the user, e.g. ``~/Applications``."""
        return expand_user("~/Applications")

    @property
    def _site_applications_dirs(self) -> list[str]:
        return ["/Applications"]

    @property
    def user_runtime_dir(self) -> str:
        """Runtime directory tied to the user, e.g. ``~/Library/Caches/TemporaryItems/$appname/$version``."""
        return self._append_app_name_and_version(
            expand_user("~/Library/Caches/TemporaryItems"), private=True, strict=True
        )


def _homebrew_prefix() -> str | None:
    if match := _HOMEBREW_PYTHON.fullmatch(sys.base_prefix):
        return match["prefix"]
    return None


class MacOS(XDGMixin, _MacOSDefaults):
    """Platform directories for the macOS operating system.

    Follows the guidance from `Apple documentation
    <https://developer.apple.com/library/archive/documentation/FileManagement/Conceptual/FileSystemProgrammingGuide/MacOSXDirectories/MacOSXDirectories.html>`_.
    Makes use of the `appname <platformdirs.api.PlatformDirsABC.appname>`, `version
    <platformdirs.api.PlatformDirsABC.version>`, `ensure_exists <platformdirs.api.PlatformDirsABC.ensure_exists>`.

    XDG environment variables (e.g. ``$XDG_DATA_HOME``) are supported and take precedence over macOS defaults.

    """

    @property
    def site_runtime_dir(self) -> str:
        """The same checked path as ``user_runtime_dir``."""
        return self.user_runtime_dir

    def place_runtime_file(self, name: str | os.PathLike[str]) -> Path:
        """Like :meth:`~platformdirs.api.PlatformDirsABC.place_runtime_file`.

        Creates the runtime directory before validating it.

        :param name: path relative to the user runtime directory.

        :returns: the proposed file path under the user runtime directory.

        """

        def created(lookup: PlatformDirsABC) -> Path:
            lookup.ensure_exists = sys.platform != "win32"
            return lookup.user_runtime_path

        return self._place_file(created, name, strict=True)

    def _iter_runtime_dirs(self) -> Iterator[str]:
        yield from super()._iter_runtime_dirs()
        if (base := xdg_dir("XDG_RUNTIME_DIR")) and not Path(base).is_dir():
            # Placement falls back here if it cannot create the missing override.
            yield super(XDGMixin, self).user_runtime_dir

    def _find_runtime_files(self, name: str | os.PathLike[str]) -> Iterator[Path]:
        def checked(lookup: MacOS) -> Iterator[Path]:
            base = xdg_dir("XDG_RUNTIME_DIR")
            for directory in lookup.iter_runtime_paths():
                if (
                    base
                    and directory == Path(lookup._join_app_name_and_version(base))
                    and runtime_base_problem(base, missing_ok=False)
                    and directory != Path(super(XDGMixin, lookup).user_runtime_dir)
                ):
                    continue
                yield directory

        return self._find_files(checked, name)


# Homebrew links each Python formula as a framework build, and a virtual environment keeps it as sys.base_prefix.
# Homebrew's sitecustomize rewrites the Cellar keg path to the opt link, so -S or PYTHONHOME leaves the Cellar one.
# Homebrew rewrites its own prefix when bottling, so naming one here would make the macOS and Linux bottles differ.
_HOMEBREW_PYTHON: Final[re.Pattern[str]] = re.compile(
    r"""
    (?P<prefix>.+)                          # $HOMEBREW_PREFIX, as printed by `brew --prefix`
    /(?:opt/python[^/]*                     # formula link: python, python3, python@3.13 or python-freethreading
       |Cellar/python[^/]*/[0-9._abrc]+)    # formula keg, named by version as sitecustomize matches it, e.g. 3.13.7_1
    /Frameworks/PythonT?\.framework         # framework build, PythonT for python-freethreading
    /Versions/[^/]+                         # interpreter version, such as 3.13
    """,
    re.VERBOSE,
)


# Unlike the other /Library site bases, macOS ships this one world-writable and sticky, like /tmp.
_SITE_CACHE: Final[str] = "/Library/Caches"


__all__ = [
    "MacOS",
]
