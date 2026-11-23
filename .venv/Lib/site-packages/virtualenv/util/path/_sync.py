from __future__ import annotations

__lazy_modules__ = [
    "contextlib",
    "pathlib",
    "shutil",
    f"{__spec__.parent}._permission",  # ty: ignore[missing-union-attribute]  # imported modules have a spec
    f"{__spec__.parent}._win",  # ty: ignore[missing-union-attribute]  # imported modules have a spec
    f"{__spec__.parent}.windows",  # ty: ignore[missing-union-attribute]  # imported modules have a spec
]

import logging
import os
import shutil
import sys
from contextlib import suppress
from pathlib import Path
from stat import S_IMODE, S_ISDIR, S_ISLNK, S_IWUSR, S_IXGRP, S_IXOTH, S_IXUSR
from typing import TYPE_CHECKING, Final

from ._permission import owner_executable_mode
from .windows import windows_extended_path

if os.name == "nt":
    from stat import FILE_ATTRIBUTE_READONLY

    from ._win import delete_readonly

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import TracebackType

    _ExcInfo = BaseException | tuple[type[BaseException], BaseException, TracebackType]

_LOGGER: Final[logging.Logger] = logging.getLogger(__name__)


def ensure_within(root: Path, path: Path) -> None:
    """Make sure a path stays inside a root folder, creating its folders and refusing links along the way.

    :param root: the folder the path must stay inside
    :param path: the path to check, below the root

    :raises ValueError: when the path leaves the root
    :raises NotADirectoryError: when a folder on the way is a link or a mount point instead of a real directory

    """
    parts: Final[tuple[str, ...]] = path.relative_to(root).parts
    if ".." in parts:
        msg: Final[str] = f"environment directory {path} must remain inside {root}"
        raise ValueError(msg)
    ensure_dir(root)
    folder = root
    # PyPy 3.9 exposes st_reparse_tag but omits IO_REPARSE_TAG_MOUNT_POINT from stat.
    mount_point_tag: Final[int] = 0xA0000003
    for part in parts:
        folder /= part
        try:
            metadata: Final[os.stat_result] = folder.lstat()
        except FileNotFoundError:
            pass
        else:
            if os.name == "nt" and metadata.st_reparse_tag == mount_point_tag:
                _LOGGER.warning("replace environment directory junction %s", folder)
                folder.rmdir()
            elif S_ISLNK(metadata.st_mode):
                _LOGGER.warning("replace environment directory link %s", folder)
                folder.unlink()
        try:
            folder.mkdir()
        except FileExistsError:
            created: Final[os.stat_result] = folder.lstat()
            if not S_ISDIR(created.st_mode) or (os.name == "nt" and created.st_reparse_tag == mount_point_tag):
                msg: Final[str] = f"environment directory is not a real directory: {folder}"
                raise NotADirectoryError(msg) from None


def ensure_dir(path: Path) -> None:
    """Create a folder and its parents when it does not exist.

    :param path: the folder to create

    """
    if not path.exists():
        _LOGGER.debug("create folder %s", path)
        os.makedirs(str(path))


def write_file(path: Path, data: bytes) -> None:
    """Write bytes to a file, replacing any existing file or link.

    :param path: the file to write
    :param data: the bytes to write

    """
    if path.is_symlink() or path.exists():
        remove_file(path)
    # Exclusive creation rejects links introduced after the old entry was removed.
    with path.open("xb") as stream:
        stream.write(data)


def remove_file(path: Path) -> None:
    """Remove a file, retrying read-only deletion on Windows when needed.

    :param path: the file to remove

    """
    try:
        path.unlink()
    except PermissionError:
        # Windows refuses to delete a read-only file, while POSIX deletion depends on the parent directory
        if os.name != "nt" or path.is_symlink():
            raise
        delete_readonly(str(path))


def symlink(src: Path, dest: Path) -> None:
    """Create a symbolic link at the destination, pointing at the source.

    :param src: the path the link points at
    :param dest: the path of the link to create

    """
    _ensure_safe_to_do(src, dest)
    _LOGGER.debug("symlink %s", _Debug(src, dest))
    dest.symlink_to(src, target_is_directory=src.is_dir())


def _ensure_safe_to_do(src: Path, dest: Path) -> None:
    if src == dest:
        msg = f"source and destination is the same {src}"
        raise ValueError(msg)
    if not dest.exists() and not dest.is_symlink():
        return
    if dest.is_dir() and not dest.is_symlink():
        _LOGGER.debug("remove directory %s", dest)
        safe_delete(dest)
    else:
        _LOGGER.debug("remove file %s", dest)
        remove_file(dest)


def safe_delete(dest: Path) -> None:
    """Delete a file or folder tree, retrying read-only entries on Windows.

    :param dest: the path to delete

    """

    def onerror(func: Callable[[str], object], path: str, exc_info: _ExcInfo) -> None:
        exc = exc_info[1] if isinstance(exc_info, tuple) else exc_info
        if isinstance(exc, FileNotFoundError):
            return
        # POSIX deletion depends on the parent directory, so changing the entry's mode cannot help.
        if (
            os.name != "nt"
            or func not in {os.unlink, os.rmdir}
            or os.path.islink(path)
            or not os.lstat(path).st_file_attributes & FILE_ATTRIBUTE_READONLY
        ):
            raise exc
        delete_readonly(path)

    target = str(dest)
    if os.name == "nt":
        target = windows_extended_path(target)
    if sys.version_info >= (3, 12):
        shutil.rmtree(target, onexc=onerror)
    else:
        shutil.rmtree(target, onerror=onerror)


class _Debug:
    def __init__(self, src: Path, dest: Path) -> None:
        self.src = src
        self.dest = dest

    def __str__(self) -> str:
        return f"{'directory ' if self.src.is_dir() else ''}{self.src!s} to {self.dest!s}"


def safe_delete_read_only(dest: Path) -> None:
    """Delete a folder tree that may hold directories closed by ``make_tree_read_only``.

    :param dest: the path to delete

    """
    if os.name == "posix":
        with suppress(FileNotFoundError):
            # a descriptor cannot be redirected by a link swapped in while the tree is walked
            for _, _, _, directory in os.fwalk(str(dest)):
                mode = os.fstat(directory).st_mode
                if not mode & S_IWUSR:
                    os.fchmod(directory, mode | S_IWUSR)
    safe_delete(dest)


def copy(src: Path, dest: Path, *, executable: bool = False) -> None:
    """Copy a file, or a folder tree, to the destination.

    :param src: the file or folder to copy
    :param dest: the destination path
    :param executable: request execute permissions when copying a single file

    """
    _LOGGER.debug("copy %s", _Debug(src, dest))
    if src.is_dir():
        _ensure_safe_to_do(src, dest)
        _copytree(src, dest, (src.resolve(),))
    else:
        _copy_file(src, dest, executable=executable)


def _copytree(src: Path, dest: Path, ancestors: tuple[Path, ...]) -> None:
    for root, dirnames, files in os.walk(src):
        dest_dir: Final[Path] = dest / os.path.relpath(root, src)
        dest_dir.mkdir(parents=True, exist_ok=True)
        for name in files:
            _copy_file(Path(root) / name, dest_dir / name)
        for name in dirnames:
            link: Final[Path] = Path(root) / name
            if not link.is_symlink():
                continue
            # os.walk does not descend into a symlinked directory, so its content is copied the way a symlinked file is
            target: Final[Path] = link.resolve()
            if any(ancestor.is_relative_to(target) for ancestor in ancestors):
                _LOGGER.warning("skip symlinked directory %s, it points at one of its own parents", link)
                continue
            _copytree(link, dest_dir / name, (*ancestors, target))


def _copy_file(src: Path, dest: Path, *, executable: bool = False) -> None:
    _ensure_safe_to_do(src, dest)
    mode: Final[int] = 0o755 if executable or src.stat().st_mode & (S_IXUSR | S_IXGRP | S_IXOTH) else 0o644
    flags: Final[int] = os.O_WRONLY | os.O_CREAT | os.O_EXCL | (os.O_BINARY if os.name == "nt" else 0)
    with src.open("rb") as source, os.fdopen(os.open(str(dest), flags, mode), "wb") as target:
        if executable and os.name == "posix":
            created = S_IMODE(os.fstat(target.fileno()).st_mode)
            if (allowed := owner_executable_mode(dest.parent, created)) != created:
                os.fchmod(target.fileno(), allowed)
        shutil.copyfileobj(source, target, length=1024 * 1024)


__all__ = [
    "copy",
    "ensure_dir",
    "ensure_within",
    "remove_file",
    "safe_delete",
    "safe_delete_read_only",
    "symlink",
    "write_file",
]
