"""Base API."""

from __future__ import annotations

__lazy_modules__ = [
    "copy",
    "pathlib",
    f"{__spec__.parent}._paths",  # ty: ignore[missing-union-attribute]  # imported modules have a spec
]

import os
import sys
from abc import ABC, abstractmethod
from copy import copy
from pathlib import Path

from ._paths import create_checked_directories, make_directories

TYPE_CHECKING = False  #: :data:`typing.TYPE_CHECKING` without importing :mod:`typing` at runtime
if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator
    from typing import Literal, Self


class PlatformDirsABC(ABC):  # ruff:ignore[too-many-public-methods]  # full directory API  # simplint: ignore[missing-from-all]  # preserve star imports
    """Abstract base class defining all platform directory properties, their :class:`~pathlib.Path` variants, and
    iterators.

    Platform-specific subclasses (e.g. :class:`~platformdirs.windows.Windows`, :class:`~platformdirs.macos.MacOS`,
    :class:`~platformdirs.unix.Unix`) implement the abstract properties to return the appropriate paths for each
    operating system.

    """

    def __init__(  # ruff:ignore[too-many-arguments, too-many-positional-arguments]  # preserve positional API
        self,
        appname: str | None = None,
        appauthor: str | Literal[False] | None = None,
        version: str | None = None,
        roaming: bool = False,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
        multipath: bool = False,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
        opinion: bool = True,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
        ensure_exists: bool = False,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
        use_site_for_root: bool = False,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # preserve positional API
    ) -> None:
        """Create a new platform directory.

        :param appname: See `appname`.
        :param appauthor: See `appauthor`.
        :param version: See `version`.
        :param roaming: See `roaming`.
        :param multipath: See `multipath`.
        :param opinion: See `opinion`.
        :param ensure_exists: See `ensure_exists`.
        :param use_site_for_root: See `use_site_for_root`.

        """
        self.appname = appname
        self.appauthor = appauthor
        self.version = version
        self.roaming = roaming
        """Whether to use the roaming appdata directory on Windows.

        That means that for users on a Windows network setup for roaming profiles, this user data will be synced on
        login (see `here <https://technet.microsoft.com/en-us/library/cc766489(WS.10).aspx>`_).

        """
        self.multipath = multipath
        """An optional parameter which indicates that the entire list of data dirs should be returned.

        When ``False``, only the first item is returned. Affects ``site_data_dir``, ``site_config_dir`` and
        ``site_applications_dir`` on Unix and macOS, and ``site_cache_dir`` on macOS under Homebrew. All but
        ``site_applications_dir`` raise :class:`ValueError` under it when `appname` or `version` contains
        :data:`os.pathsep`.

        """
        self.opinion = opinion
        """Whether to use opinionated values.

        When enabled, appends an additional subdirectory for certain directories: e.g. ``Cache`` for cache and ``Logs``
        for logs on Windows, ``log`` for logs on Unix.

        """
        self.ensure_exists = ensure_exists
        """Create the directory a property returns, with missing parents, each time the property is read.

        Media directories qualify only when the user set them through XDG. platformdirs never creates fonts, bin,
        applications or default media directories. Off by default.

        """
        self.use_site_for_root = use_site_for_root
        """Whether to redirect ``user_*_dir`` calls to their ``site_*_dir`` equivalents when the effective uid is 0.

        Only has an effect on Unix. Disabled by default for backwards compatibility. When enabled, XDG user environment
        variables (e.g. ``XDG_DATA_HOME``) are bypassed for the redirected directories.

        """

    @property
    def appname(self) -> str | None:
        """The name of the application."""
        return self._appname

    @appname.setter
    def appname(self, value: str | None) -> None:
        _ensure_inside_base("appname", value)
        self._appname = value

    @property
    def appauthor(self) -> str | Literal[False] | None:
        """The name of the app author or distributing body for this application.

        Typically, it is the owning company name. Defaults to `appname`. You may pass ``False`` to disable it.

        .. note::

            On Windows, the directory structure is ``<base>/<appauthor>/<appname>``. When ``appauthor`` is ``None`` (the
            default), it falls back to ``appname``, resulting in ``<base>/<appname>/<appname>`` (e.g.
            ``AppData/Local/myapp/myapp``). Pass ``appauthor=False`` to omit the author directory entirely and get
            ``<base>/<appname>``.

        """
        return self._appauthor

    @appauthor.setter
    def appauthor(self, value: str | Literal[False] | None) -> None:
        _ensure_inside_base("appauthor", value)
        self._appauthor = value

    @property
    def version(self) -> str | None:
        """An optional version path element to append to the path.

        You might want to use this if you want multiple versions of your app to be able to run independently. If used,
        this would typically be ``<major>.<minor>``.

        """
        return self._version

    @version.setter
    def version(self, value: str | None) -> None:
        _ensure_inside_base("version", value)
        self._version = value

    @property
    def user_data_path(self) -> Path:
        """Data path tied to the user."""
        return Path(self.user_data_dir)

    @property
    @abstractmethod
    def user_data_dir(self) -> str:
        """Data directory tied to the user."""

    @property
    def site_data_path(self) -> Path:
        """Data path shared by users. Only return the first item, even if ``multipath`` is set to ``True``."""
        return self._first_site_dir_as_path(self._site_data_dirs)

    def _first_site_dir_as_path(self, dirs: list[str]) -> Path:
        # A *_path property always returns the first entry, regardless of multipath, so only that entry is created.
        path = dirs[0]
        self._optionally_create_directory(path, private=False, site=True)
        return Path(path)

    def _optionally_create_directory(
        self, path: str, *, private: bool, site: bool = False, strict: bool = False
    ) -> None:
        if not self.ensure_exists:
            return
        _ensure_home_known(path)
        self._create_directory(Path(path), private=private, site=site, strict=strict)

    def _create_directory(  # ruff:ignore[no-self-use]  # Unix override hook
        self,
        path: Path,
        *,
        private: bool,
        site: bool,  # Unix override hook
        strict: bool,
    ) -> None:
        if site or sys.platform == "win32":
            make_directories(path, private=private)
        else:
            create_checked_directories(path, private=private, policy="runtime" if strict else "user")

    @property
    def _site_data_dirs(self) -> list[str]:
        return [self.site_data_dir]

    @property
    @abstractmethod
    def site_data_dir(self) -> str:
        """Data directory shared by users."""

    @property
    def user_config_path(self) -> Path:
        """Config path tied to the user."""
        return Path(self.user_config_dir)

    @property
    @abstractmethod
    def user_config_dir(self) -> str:
        """Config directory tied to the user."""

    @property
    def site_config_path(self) -> Path:
        """Config path shared by users. Only return the first item, even if ``multipath`` is set to ``True``."""
        return self._first_site_dir_as_path(self._site_config_dirs)

    @property
    def _site_config_dirs(self) -> list[str]:
        return [self.site_config_dir]

    @property
    @abstractmethod
    def site_config_dir(self) -> str:
        """Config directory shared by users."""

    @property
    def user_cache_path(self) -> Path:
        """Cache path tied to the user."""
        return Path(self.user_cache_dir)

    @property
    @abstractmethod
    def user_cache_dir(self) -> str:
        """Cache directory tied to the user."""

    @property
    def site_cache_path(self) -> Path:
        """Cache path shared by users. Only return the first item, even if ``multipath`` is set to ``True``."""
        return self._first_site_dir_as_path(self._site_cache_dirs)

    @property
    def _site_cache_dirs(self) -> list[str]:
        return [self.site_cache_dir]

    @property
    @abstractmethod
    def site_cache_dir(self) -> str:
        """Cache directory shared by users."""

    @property
    def user_state_path(self) -> Path:
        """State path tied to the user."""
        return Path(self.user_state_dir)

    @property
    @abstractmethod
    def user_state_dir(self) -> str:
        """State directory tied to the user."""

    @property
    def site_state_path(self) -> Path:
        """State path shared by users."""
        return Path(self.site_state_dir)

    @property
    @abstractmethod
    def site_state_dir(self) -> str:
        """State directory shared by users."""

    @property
    def user_log_path(self) -> Path:
        """Log path tied to the user."""
        return Path(self.user_log_dir)

    @property
    @abstractmethod
    def user_log_dir(self) -> str:
        """Log directory tied to the user."""

    @property
    def site_log_path(self) -> Path:
        """Log path shared by users."""
        return Path(self.site_log_dir)

    @property
    @abstractmethod
    def site_log_dir(self) -> str:
        """Log directory shared by users."""

    @property
    def user_documents_path(self) -> Path:
        """Documents path tied to the user."""
        return Path(self.user_documents_dir)

    @property
    @abstractmethod
    def user_documents_dir(self) -> str:
        """Documents directory tied to the user."""

    @property
    def user_downloads_path(self) -> Path:
        """Downloads path tied to the user."""
        return Path(self.user_downloads_dir)

    @property
    @abstractmethod
    def user_downloads_dir(self) -> str:
        """Downloads directory tied to the user."""

    @property
    def user_pictures_path(self) -> Path:
        """Pictures path tied to the user."""
        return Path(self.user_pictures_dir)

    @property
    @abstractmethod
    def user_pictures_dir(self) -> str:
        """Pictures directory tied to the user."""

    @property
    def user_videos_path(self) -> Path:
        """Videos path tied to the user."""
        return Path(self.user_videos_dir)

    @property
    @abstractmethod
    def user_videos_dir(self) -> str:
        """Videos directory tied to the user."""

    @property
    def user_music_path(self) -> Path:
        """Music path tied to the user."""
        return Path(self.user_music_dir)

    @property
    @abstractmethod
    def user_music_dir(self) -> str:
        """Music directory tied to the user."""

    @property
    def user_desktop_path(self) -> Path:
        """Desktop path tied to the user."""
        return Path(self.user_desktop_dir)

    @property
    @abstractmethod
    def user_desktop_dir(self) -> str:
        """Desktop directory tied to the user."""

    @property
    def user_projects_path(self) -> Path:
        """Projects path tied to the user."""
        return Path(self.user_projects_dir)

    @property
    @abstractmethod
    def user_projects_dir(self) -> str:
        """Projects directory tied to the user."""

    @property
    def user_publicshare_path(self) -> Path:
        """Public share path tied to the user."""
        return Path(self.user_publicshare_dir)

    @property
    @abstractmethod
    def user_publicshare_dir(self) -> str:
        """Public share directory tied to the user."""

    @property
    def user_templates_path(self) -> Path:
        """Templates path tied to the user."""
        return Path(self.user_templates_dir)

    @property
    @abstractmethod
    def user_templates_dir(self) -> str:
        """Templates directory tied to the user."""

    @property
    def user_fonts_path(self) -> Path:
        """Fonts path tied to the user."""
        return Path(self.user_fonts_dir)

    @property
    @abstractmethod
    def user_fonts_dir(self) -> str:
        """Fonts directory tied to the user."""

    @property
    def user_preference_path(self) -> Path:
        """Preference path tied to the user."""
        return Path(self.user_preference_dir)

    @property
    @abstractmethod
    def user_preference_dir(self) -> str:
        """Preference directory tied to the user."""

    @property
    def user_bin_path(self) -> Path:
        """Bin path tied to the user."""
        return Path(self.user_bin_dir)

    @property
    @abstractmethod
    def user_bin_dir(self) -> str:
        """Bin directory tied to the user."""

    @property
    def site_bin_path(self) -> Path:
        """Bin path shared by users."""
        return Path(self.site_bin_dir)

    @property
    @abstractmethod
    def site_bin_dir(self) -> str:
        """Bin directory shared by users."""

    @property
    def user_applications_path(self) -> Path:
        """Applications path tied to the user."""
        return Path(self.user_applications_dir)

    @property
    @abstractmethod
    def user_applications_dir(self) -> str:
        """Applications directory tied to the user."""

    @property
    def site_applications_path(self) -> Path:
        """Applications path shared by users. Only return the first item, even if ``multipath`` is set to ``True``."""
        return Path(self._site_applications_dirs[0])

    @property
    def _site_applications_dirs(self) -> list[str]:
        return [self.site_applications_dir]

    @property
    @abstractmethod
    def site_applications_dir(self) -> str:
        """Applications directory shared by users."""

    @property
    def user_runtime_path(self) -> Path:
        """Runtime path tied to the user."""
        return Path(self.user_runtime_dir)

    @property
    @abstractmethod
    def user_runtime_dir(self) -> str:
        """Runtime directory tied to the user."""

    @property
    def site_runtime_path(self) -> Path:
        """Runtime path shared by users."""
        return Path(self.site_runtime_dir)

    @property
    @abstractmethod
    def site_runtime_dir(self) -> str:
        """Runtime directory shared by users."""

    def _append_app_name_and_version(self, *base: str, private: bool, strict: bool = False) -> str:
        path = self._join_app_name_and_version(*base)
        self._optionally_create_directory(path, private=private, site=not private, strict=strict)
        return path

    def _join_app_name_and_version(self, *base: str) -> str:
        params = list(base[1:])
        if self.appname:
            params.append(self.appname)
            if self.version:
                params.append(self.version)
        return os.path.join(base[0], *params)  # ruff:ignore[os-path-join]  # preserve path separators

    def _optionally_create_media_directory(self, path: str) -> None:
        # Only called for a media directory the user configured. Media directories are often symlinks to removable or
        # network storage, so a dangling link is returned as-is, like before ensure_exists covered them.
        try:
            self._optionally_create_directory(path, private=False)
        except FileExistsError:
            if not (directory := Path(path)).is_symlink() or directory.exists():
                raise

    def _select_site_dirs(self, dirs: list[str]) -> str:
        # Site lists are built without touching the disk, so ensure_exists only creates what the caller gets back.
        selected = dirs if self.multipath else dirs[:1]
        if self.multipath and any(os.pathsep in path for path in selected):
            # Callers split the joined string on os.pathsep, so a separator inside one entry reads as two directories.
            msg = f"multipath cannot join site directories that contain {os.pathsep!r}, got {selected!r}"
            raise ValueError(msg)
        for path in selected:
            self._optionally_create_directory(path, private=False, site=True)
        return os.pathsep.join(selected)

    def iter_config_paths(self) -> Iterator[Path]:
        """:yields: all user and site configuration paths."""
        for path in self.iter_config_dirs():
            yield Path(path)

    def iter_config_dirs(self) -> Iterator[str]:
        """:yields: all user and site configuration directories."""
        yield from _unique(self._iter_config_dirs())

    def _iter_config_dirs(self) -> Iterator[str]:
        if not self._use_site:
            yield self.user_config_dir
        yield from self._create_as_yielded(self._site_config_dirs)

    @property
    def _use_site(self) -> bool:
        # Only Unix redirects root's user dirs to the site ones. The iterators then skip the user dir, since under
        # multipath it is the joined site string that _unique cannot match against any single entry.
        return False

    def _create_as_yielded(self, dirs: Iterable[str]) -> Iterator[str]:
        for path in dirs:
            self._optionally_create_directory(path, private=False, site=True)
            yield path

    def iter_data_paths(self) -> Iterator[Path]:
        """:yields: all user and site data paths."""
        for path in self.iter_data_dirs():
            yield Path(path)

    def iter_data_dirs(self) -> Iterator[str]:
        """:yields: all user and site data directories."""
        yield from _unique(self._iter_data_dirs())

    def _iter_data_dirs(self) -> Iterator[str]:
        if not self._use_site:
            yield self.user_data_dir
        yield from self._create_as_yielded(self._site_data_dirs)

    def iter_cache_paths(self) -> Iterator[Path]:
        """:yields: all user and site cache paths."""
        for path in self.iter_cache_dirs():
            yield Path(path)

    def iter_cache_dirs(self) -> Iterator[str]:
        """:yields: all user and site cache directories."""
        yield from _unique(self._iter_cache_dirs())

    def _iter_cache_dirs(self) -> Iterator[str]:
        if not self._use_site:
            yield self.user_cache_dir
        yield from self._create_as_yielded(self._site_cache_dirs)

    def iter_state_paths(self) -> Iterator[Path]:
        """:yields: all user and site state paths."""
        for path in self.iter_state_dirs():
            yield Path(path)

    def iter_state_dirs(self) -> Iterator[str]:
        """:yields: all user and site state directories."""
        yield from _unique(self._iter_state_dirs())

    def _iter_state_dirs(self) -> Iterator[str]:
        if not self._use_site:
            yield self.user_state_dir
        yield self.site_state_dir

    def iter_log_paths(self) -> Iterator[Path]:
        """:yields: all user and site log paths."""
        for path in self.iter_log_dirs():
            yield Path(path)

    def iter_log_dirs(self) -> Iterator[str]:
        """:yields: all user and site log directories."""
        yield from _unique(self._iter_log_dirs())

    def _iter_log_dirs(self) -> Iterator[str]:
        if not self._use_site:
            yield self.user_log_dir
        yield self.site_log_dir

    def iter_runtime_paths(self) -> Iterator[Path]:
        """:yields: all user and site runtime paths."""
        for path in self.iter_runtime_dirs():
            yield Path(path)

    def iter_runtime_dirs(self) -> Iterator[str]:
        """:yields: all user and site runtime directories."""
        yield from _unique(self._iter_runtime_dirs())

    def _iter_runtime_dirs(self) -> Iterator[str]:
        yield self.user_runtime_dir
        # Root's user runtime dir is already the site one; site_runtime_dir reads the invoking user's XDG_RUNTIME_DIR.
        if not self._use_site:
            yield self.site_runtime_dir

    def place_config_file(self, name: str | os.PathLike[str]) -> Path:
        """Return the path of ``name`` under `user_config_path`, creating the missing directories on the way.

        Each directory it creates, including the user directory itself, gets mode ``0o700`` whether or not
        `ensure_exists` is set; directories that already exist keep their mode. On Unix, root with `use_site_for_root`
        places the file under the site directory. New directories use mode ``0755`` subject to the umask. The caller
        creates the file.

        :param name: file path relative to the user directory, e.g. ``"sub/app.toml"``.

        :returns: the path of ``name`` under the user directory.

        :raises ValueError: if ``name`` is empty, absolute, has a drive or climbs out through ``..``.
        :raises RuntimeError: if the user directory starts with ``~`` because the home directory is unknown.
        :raises OSError: if it cannot create a missing directory, e.g. one on a missing drive or network share.

        """
        return self._place_file(lambda dirs: dirs.user_config_path, name)

    def _place_file(
        self, user_path: Callable[[PlatformDirsABC], Path], name: str | os.PathLike[str], *, strict: bool = False
    ) -> Path:
        _ensure_inside_base("name", relative := os.fspath(name))
        if not Path(relative).parts:
            msg = f"name must point to a file, got {relative!r}"
            raise ValueError(msg)
        # Under ensure_exists the lookup itself would create the user directory with the default mode, not 0o700.
        (lookup := copy(self)).ensure_exists = False
        # Under multipath *_dir joins the site directories with os.pathsep, so place under the single *_path.
        _ensure_home_known(str(directory := user_path(lookup)))
        path = directory / relative
        site = self._use_site
        self._create_directory(path.parent, private=not site, site=site, strict=strict or site)
        return path

    def place_data_file(self, name: str | os.PathLike[str]) -> Path:
        """Like `place_config_file`, under `user_data_path`.

        :param name: see `place_config_file`.

        :returns: the path of ``name`` under the user data directory.

        """
        return self._place_file(lambda dirs: dirs.user_data_path, name)

    def place_cache_file(self, name: str | os.PathLike[str]) -> Path:
        """Like `place_config_file`, under `user_cache_path`.

        :param name: see `place_config_file`.

        :returns: the path of ``name`` under the user cache directory.

        """
        return self._place_file(lambda dirs: dirs.user_cache_path, name)

    def place_state_file(self, name: str | os.PathLike[str]) -> Path:
        """Like `place_config_file`, under `user_state_path`.

        :param name: see `place_config_file`.

        :returns: the path of ``name`` under the user state directory.

        """
        return self._place_file(lambda dirs: dirs.user_state_path, name)

    def place_log_file(self, name: str | os.PathLike[str]) -> Path:
        """Like `place_config_file`, under `user_log_path`.

        :param name: see `place_config_file`.

        :returns: the path of ``name`` under the user log directory.

        """
        return self._place_file(lambda dirs: dirs.user_log_path, name)

    def place_runtime_file(self, name: str | os.PathLike[str]) -> Path:
        """Like `place_config_file`, under `user_runtime_path`.

        :param name: see `place_config_file`.

        :returns: the path of ``name`` under the user runtime directory.

        :raises PermissionError: on Unix, if another user owns the temporary fallback directory.

        """
        return self._place_file(lambda dirs: dirs.user_runtime_path, name)

    def find_config_file(self, name: str | os.PathLike[str]) -> Path | None:
        """Find the first ``name`` file in :meth:`iter_config_paths` order, without creating any directory.

        :param name: path relative to each directory, may contain subdirectories.

        :returns: the file, or ``None`` when no directory holds one.

        :raises ValueError: if ``name`` is absolute, has a drive or climbs out with ``..``.

        """
        return next(self._find_files(lambda dirs: dirs.iter_config_paths(), name), None)

    def _find_files(self, iter_paths: Callable[[Self], Iterator[Path]], name: str | os.PathLike[str]) -> Iterator[Path]:
        _ensure_inside_base("name", relative := os.fspath(name))
        # The iterators create each directory they yield under ensure_exists, and a lookup must only read the disk.
        (lookup := copy(self)).ensure_exists = False
        return (path for directory in iter_paths(lookup) if os.path.isfile(path := directory / relative))  # ruff:ignore[os-path-isfile]  # Path.is_file raises on an unsearchable directory before Python 3.14

    def find_config_files(self, name: str | os.PathLike[str]) -> list[Path]:
        """Find every ``name`` file in :meth:`iter_config_paths` order, without creating any directory.

        :param name: see :meth:`find_config_file`.

        :returns: the files, user directory first.

        :raises ValueError: see :meth:`find_config_file`.

        """
        return list(self._find_files(lambda dirs: dirs.iter_config_paths(), name))

    def find_data_file(self, name: str | os.PathLike[str]) -> Path | None:
        """Like :meth:`find_config_file`, searching :meth:`iter_data_paths`.

        :param name: see :meth:`find_config_file`.

        :returns: the first ``name`` file in the data paths, or ``None`` when no directory holds one.

        """
        return next(self._find_files(lambda dirs: dirs.iter_data_paths(), name), None)

    def find_data_files(self, name: str | os.PathLike[str]) -> list[Path]:
        """Like :meth:`find_config_files`, searching :meth:`iter_data_paths`.

        :param name: see :meth:`find_config_file`.

        :returns: every ``name`` file in the data paths, in iteration order.

        """
        return list(self._find_files(lambda dirs: dirs.iter_data_paths(), name))

    def find_cache_file(self, name: str | os.PathLike[str]) -> Path | None:
        """Like :meth:`find_config_file`, searching :meth:`iter_cache_paths`.

        :param name: see :meth:`find_config_file`.

        :returns: the first ``name`` file in the cache paths, or ``None`` when no directory holds one.

        """
        return next(self._find_files(lambda dirs: dirs.iter_cache_paths(), name), None)

    def find_cache_files(self, name: str | os.PathLike[str]) -> list[Path]:
        """Like :meth:`find_config_files`, searching :meth:`iter_cache_paths`.

        :param name: see :meth:`find_config_file`.

        :returns: every ``name`` file in the cache paths, in iteration order.

        """
        return list(self._find_files(lambda dirs: dirs.iter_cache_paths(), name))

    def find_state_file(self, name: str | os.PathLike[str]) -> Path | None:
        """Like :meth:`find_config_file`, searching :meth:`iter_state_paths`.

        :param name: see :meth:`find_config_file`.

        :returns: the first ``name`` file in the state paths, or ``None`` when no directory holds one.

        """
        return next(self._find_files(lambda dirs: dirs.iter_state_paths(), name), None)

    def find_state_files(self, name: str | os.PathLike[str]) -> list[Path]:
        """Like :meth:`find_config_files`, searching :meth:`iter_state_paths`.

        :param name: see :meth:`find_config_file`.

        :returns: every ``name`` file in the state paths, in iteration order.

        """
        return list(self._find_files(lambda dirs: dirs.iter_state_paths(), name))

    def find_log_file(self, name: str | os.PathLike[str]) -> Path | None:
        """Like :meth:`find_config_file`, searching :meth:`iter_log_paths`.

        :param name: see :meth:`find_config_file`.

        :returns: the first ``name`` file in the log paths, or ``None`` when no directory holds one.

        """
        return next(self._find_files(lambda dirs: dirs.iter_log_paths(), name), None)

    def find_log_files(self, name: str | os.PathLike[str]) -> list[Path]:
        """Like :meth:`find_config_files`, searching :meth:`iter_log_paths`.

        :param name: see :meth:`find_config_file`.

        :returns: every ``name`` file in the log paths, in iteration order.

        """
        return list(self._find_files(lambda dirs: dirs.iter_log_paths(), name))

    def find_runtime_file(self, name: str | os.PathLike[str]) -> Path | None:
        """Like :meth:`find_config_file`, searching :meth:`iter_runtime_paths`.

        :param name: see :meth:`find_config_file`.

        :returns: the first ``name`` file in the runtime paths, or ``None`` when no directory holds one.

        """
        return next(self._find_runtime_files(name), None)

    def _find_runtime_files(self, name: str | os.PathLike[str]) -> Iterator[Path]:
        return self._find_files(lambda dirs: dirs.iter_runtime_paths(), name)

    def find_runtime_files(self, name: str | os.PathLike[str]) -> list[Path]:
        """Like :meth:`find_config_files`, searching :meth:`iter_runtime_paths`.

        :param name: see :meth:`find_config_file`.

        :returns: every ``name`` file in the runtime paths, in iteration order.

        """
        return list(self._find_runtime_files(name))


def _ensure_inside_base(name: str, value: str | Literal[False] | None) -> None:
    if not value:
        return
    # os.path.join discards the base when a later component has a root or a drive, and ``..`` climbs out of it.
    drive, tail = os.path.splitdrive(value)
    if drive or tail.startswith(("/", "\\")) or ".." in tail.replace("\\", "/").split("/"):
        msg = f"{name} must stay inside the base directory, got {value!r}"
        raise ValueError(msg)


def _ensure_home_known(path: str) -> None:
    # expanduser leaves "~" when the home is unknown, and creating it would make a "~" directory in the cwd.
    if path.startswith("~"):
        msg = f"could not determine the home directory, refusing to create {path!r}"
        raise RuntimeError(msg)


def _unique(dirs: Iterable[str]) -> Iterator[str]:
    # :yield: ``dirs`` in order, skipping any directory already yielded.
    # Lazy on purpose: under ensure_exists reading a site_*_dir creates it, so draining ``dirs`` up front would
    # create directories for a caller that stops after the first entry.
    seen: set[Path] = set()
    for path in dirs:
        if (normalized := Path(path)) not in seen:
            seen.add(normalized)
            yield path


class RuntimeDirWarning(UserWarning):  # simplint: ignore[missing-from-all]  # preserve star imports
    """Emitted when the Unix or macOS ``user_runtime_dir`` cannot use ``$XDG_RUNTIME_DIR``."""
