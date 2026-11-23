"""Atomic publication and removal of strict soft-lock claim records."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from importlib.machinery import ModuleSpec

__spec__ = cast("ModuleSpec", __spec__)

__lazy_modules__ = [
    "contextlib",
    "filelock._core",
    "filelock._filesystem",
    "pathlib",
    "tempfile",
    f"{__spec__.parent}._claims",
    f"{__spec__.parent}._directories",
    f"{__spec__.parent}._windows",
]

import contextlib
import errno
import os
import stat
import sys
import tempfile
import time
from errno import EACCES, EINVAL, ENOSYS, EPERM, EXDEV
from pathlib import Path
from typing import Final

from filelock._core import SoftFileLockProtocolError, raise_cleanup_errors
from filelock._filesystem import write_all

from ._claims import PrivateRecordReclaimedError, private_record_name
from ._directories import (
    O_BINARY,
    SUPPORTS,
    file_identity,
    open_claim_directory,
    open_directory,
    open_relative,
    pin_claim_directory,
    relative_identity,
)

if sys.platform == "win32":  # pragma: win32 cover
    from filelock._filesystem import cancelling_oplock_wait

    from ._windows import mark_claim_for_deletion

if TYPE_CHECKING:
    from collections.abc import Callable

    from filelock._core import FileLockContext


def _probe_link_follow_symlinks() -> bool:
    # Some runtimes advertise no-follow links but reject them. A failed temporary directory cannot test support.
    if not SUPPORTS.has_link:
        return False
    try:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory, "probe-source")
            source.touch()
            return _probe_link_option(source, Path(directory, "probe-link"))
    except OSError:
        return SUPPORTS.link_follow_symlinks


def _probe_link_option(source: Path, destination: Path) -> bool:
    try:
        os.link(source, destination, follow_symlinks=False)
    except (NotImplementedError, ValueError):
        return False
    except OSError as error:
        return error.errno != EINVAL and SUPPORTS.link_follow_symlinks
    return True


_LINK_HONORS_FOLLOW_SYMLINKS: Final[bool] = _probe_link_follow_symlinks()


def _probe_hard_link_unsupported_errnos() -> frozenset[int]:
    # Some runtimes omit ENOTSUP. Prefer its native value where the two errnos differ.
    not_supported = getattr(errno, "ENOTSUP", getattr(errno, "EOPNOTSUPP", None))
    return frozenset({ENOSYS, EXDEV} if not_supported is None else {ENOSYS, EXDEV, not_supported})


_HARD_LINK_UNSUPPORTED_ERRNOS: Final[frozenset[int]] = _probe_hard_link_unsupported_errnos()


def raise_recorded_errors(message: str, errors: list[BaseException]) -> None:
    if len(errors) > 1:
        raise_cleanup_errors(message, errors[0], *errors[1:])
    raise errors[0]


def publish_record(
    public_path: str,
    record: bytes,
    mode: int,
    directory_opener: Callable[[str], int] | None = None,
) -> BaseException | None:
    directory, public_name = os.path.split(public_path)
    directory = directory or os.curdir
    private_name = private_record_name(public_name)
    directory_fd = (directory_opener or open_directory)(directory) if SUPPORTS.open_dir_fd else None
    directory_ref = directory, directory_fd
    try:
        _publish_record_in_directory(directory_ref, (private_name, public_name), mode, record)
    except BaseException as publication_error:  # preserve publication and directory cleanup errors
        try:
            if directory_fd is not None:  # pragma: needs dir-fd
                os.close(directory_fd)
        except BaseException as close_error:  # ruff:ignore[blind-except]  # pragma: needs dir-fd  # preserve publication and directory cleanup errors
            raise_cleanup_errors("strict publication directory cleanup failed", publication_error, close_error)
        raise
    if directory_fd is not None:  # pragma: needs dir-fd
        try:
            os.close(directory_fd)
        except BaseException as close_error:  # ruff:ignore[blind-except]  # a claim's caller recorded its path before publishing
            return close_error
    return None


def _publish_record_in_directory(
    directory_ref: tuple[str, int | None],
    names: tuple[str, str],
    mode: int,
    record: bytes,
) -> None:
    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | O_BINARY
    if (o_nofollow := getattr(os, "O_NOFOLLOW", None)) is not None:  # pragma: needs o-nofollow
        flags |= o_nofollow
    private_fd = open_relative(directory_ref, names[0], flags, mode & ~(stat.S_IWGRP | stat.S_IWOTH))
    private_identity: tuple[int, int] | None = None
    try:
        private_identity = file_identity(os.fstat(private_fd))
        write_all(private_fd, record)
        _link_private_record(directory_ref, names, private_identity)
    except BaseException as publication_error:  # preserve publication and cleanup errors
        close_error, unlink_error = _close_and_unlink_private_record(
            directory_ref,
            names[0],
            private_fd,
            private_identity,
        )
        if close_error is not None or unlink_error is not None:
            raise_cleanup_errors(
                "strict record publication cleanup failed",
                publication_error,
                close_error,
                unlink_error,
            )
        raise
    close_error, unlink_error = _close_and_unlink_private_record(
        directory_ref,
        names[0],
        private_fd,
        private_identity,
    )
    if close_error is not None or unlink_error is not None:
        _raise_record_finalization_errors(close_error, unlink_error)


def _link_private_record(
    directory_ref: tuple[str, int | None],
    names: tuple[str, str],
    private_identity: tuple[int, int],
) -> None:
    try:
        link_or_find_committed(directory_ref, *names, private_identity)
    except FileNotFoundError as error:
        if relative_identity(directory_ref, names[0]) is not None:
            raise
        msg = "private publication record was reclaimed"
        raise PrivateRecordReclaimedError(msg) from error
    if relative_identity(directory_ref, names[1]) == private_identity:
        return
    msg_0 = "private publication record was replaced"
    raise PrivateRecordReclaimedError(msg_0)


def link_or_find_committed(
    directory_ref: tuple[str, int | None],
    source_name: str,
    destination_name: str,
    source_identity: tuple[int, int] | None = None,
) -> None:
    try:
        _link_relative(directory_ref, source_name, destination_name)
    except FileExistsError:
        # An NFS retry can return EEXIST after a successful link. Its source name may already have been reclaimed.
        if (identity := relative_identity(directory_ref, destination_name)) is None or identity != (
            source_identity or relative_identity(directory_ref, source_name)
        ):
            raise


def _link_relative(directory_ref: tuple[str, int | None], source_name: str, destination_name: str) -> None:
    directory, directory_fd = directory_ref
    if directory_fd is not None and SUPPORTS.link_dir_fd:  # pragma: needs dir-fd
        link_no_follow(source_name, destination_name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
        return
    link_no_follow(Path(directory, source_name), Path(directory, destination_name))  # pragma: win32 cover


def link_no_follow(
    source: str | Path,
    destination: str | Path,
    *,
    src_dir_fd: int | None = None,
    dst_dir_fd: int | None = None,
) -> None:
    if not SUPPORTS.has_link:
        msg = "os.link is unavailable on this platform"
        raise NotImplementedError(msg)
    if _LINK_HONORS_FOLLOW_SYMLINKS:
        os.link(source, destination, src_dir_fd=src_dir_fd, dst_dir_fd=dst_dir_fd, follow_symlinks=False)
    else:  # pragma: lacks link-follow-symlinks
        os.link(source, destination, src_dir_fd=src_dir_fd, dst_dir_fd=dst_dir_fd)


def _close_and_unlink_private_record(
    directory_ref: tuple[str, int | None],
    private_name: str,
    private_fd: int,
    private_identity: tuple[int, int] | None,
) -> tuple[BaseException | None, BaseException | None]:
    close_error: BaseException | None = None
    try:
        os.close(private_fd)
    except BaseException as error:  # ruff:ignore[blind-except]  # returned for grouping with unlink failures
        close_error = error
    unlink_error: BaseException | None = None
    try:
        if private_identity is None:
            unlink_relative(directory_ref, private_name)
        elif relative_identity(directory_ref, private_name) == private_identity:
            with contextlib.suppress(FileNotFoundError):
                unlink_relative(directory_ref, private_name)
    except FileNotFoundError:
        pass
    except BaseException as error:  # ruff:ignore[blind-except]  # returned for grouping with close failures
        unlink_error = error
    return close_error, unlink_error


def unlink_relative(directory_ref: tuple[str, int | None], name: str) -> None:
    directory, directory_fd = directory_ref
    if directory_fd is not None and SUPPORTS.unlink_dir_fd:  # pragma: needs dir-fd
        os.unlink(name, dir_fd=directory_fd)
    elif sys.platform == "win32":  # pragma: win32 cover
        unlink_in_directory(Path(directory), name)
    else:
        Path(directory, name).unlink()  # pragma: win32 no cover


def unlink_in_directory(
    directory: Path,
    name: str,
    *,
    claim_fd: int | None = None,
    cancel_wait: contextlib.AbstractContextManager[None] | None = None,
) -> BaseException | None:
    if claim_fd is not None:  # pragma: win32 cover
        return mark_claim_for_deletion(
            claim_fd,
            str(directory / name),
            lambda: str(directory / private_record_name(name)),
            cancel_wait=cancel_wait,
        )
    if SUPPORTS.unlink_dir_fd:  # pragma: needs dir-fd
        directory_fd = open_claim_directory(str(directory))
        try:
            os.unlink(name, dir_fd=directory_fd)
        except BaseException as unlink_error:  # preserve unlink and directory cleanup errors
            try:
                os.close(directory_fd)
            except BaseException as close_error:  # ruff:ignore[blind-except]  # preserve unlink and directory cleanup errors
                raise_cleanup_errors("strict unlink directory cleanup failed", unlink_error, close_error)
            raise
        try:
            os.close(directory_fd)
        except BaseException as close_error:  # ruff:ignore[blind-except]  # caller commits the removed path before raising
            return close_error
        return None
    if sys.platform != "win32":  # pragma: win32 no cover
        Path(directory / name).unlink()
        return None
    retry_delay = 0.001  # pragma: win32 cover
    max_retries: Final[int] = 10  # pragma: win32 cover
    for attempt in range(max_retries):  # pragma: win32 cover
        if (error := _unlink_error(directory / name)) is None:
            return None
        if error.errno not in {EACCES, EPERM} or attempt == max_retries - 1:
            raise error
        time.sleep(retry_delay)
        retry_delay *= 2
    return None  # pragma: no cover  # the final retry returns or raises


def _unlink_error(path: Path) -> OSError | None:  # pragma: win32 cover
    try:
        path.unlink()
    except OSError as error:
        return error
    return None


def _raise_record_finalization_errors(
    close_error: BaseException | None,
    unlink_error: BaseException | None,
) -> None:
    errors = [error for error in (close_error, unlink_error) if error is not None]
    if len(errors) > 1:
        raise_cleanup_errors("strict record finalization failed", errors[0], *errors[1:])
    raise errors[0]


def unlink_owner_path_result(
    path: str, context: FileLockContext, *, deadline: float | None
) -> tuple[bool, BaseException | None]:
    directory, name = os.path.split(path)
    try:
        if sys.platform == "win32":  # pragma: win32 cover
            if context.claim_descriptors is None or (fd := context.claim_descriptors.get(path)) is None:
                return True, None
            return True, unlink_in_directory(
                Path(directory),
                name,
                claim_fd=fd,
                cancel_wait=cancelling_oplock_wait(deadline) if deadline is not None else None,
            )
        with pin_claim_directory(claim_directory := Path(directory or os.curdir)):  # pragma: win32 no cover
            return True, unlink_in_directory(claim_directory, name)
    except FileNotFoundError:
        return True, None
    except BaseException as error:  # ruff:ignore[blind-except]  # keep ownership when unlink did not commit
        return False, error


def link_no_replace(  # pragma: win32 no cover
    directory: Path, source_name: str, destination_name: str
) -> BaseException | None:
    if SUPPORTS.link_dir_fd:  # pragma: needs dir-fd
        directory_fd = open_claim_directory(str(directory))
        try:
            link_or_find_committed((str(directory), directory_fd), source_name, destination_name)
        except BaseException as link_error:  # preserve link and directory cleanup errors
            try:
                os.close(directory_fd)
            except BaseException as close_error:  # ruff:ignore[blind-except]  # preserve link and directory cleanup errors
                raise_cleanup_errors("strict link directory cleanup failed", link_error, close_error)
            raise
        try:
            os.close(directory_fd)
        except BaseException as close_error:  # ruff:ignore[blind-except]  # the caller recorded the held path before linking
            return close_error
        return None
    with pin_claim_directory(directory):  # pragma: win32 cover
        link_or_find_committed((str(directory), None), source_name, destination_name)
    return None  # pragma: win32 cover


def raise_if_hard_links_unsupported(lock_file: str, error: NotImplementedError | OSError) -> None:
    windows_hard_link_unsupported: Final[frozenset[int]] = frozenset({1, 17, 50})
    unsupported = (
        isinstance(error, NotImplementedError)
        or error.errno in _HARD_LINK_UNSUPPORTED_ERRNOS
        or (getattr(error, "winerror", None) in windows_hard_link_unsupported)
    )
    if unsupported:
        reason = "filesystem does not support atomic no-replace hard-link publication"
        raise SoftFileLockProtocolError(lock_file, None, reason) from error


__all__ = [
    "link_no_follow",
    "link_no_replace",
    "link_or_find_committed",
    "publish_record",
    "raise_if_hard_links_unsupported",
    "raise_recorded_errors",
    "unlink_in_directory",
    "unlink_owner_path_result",
    "unlink_relative",
]
