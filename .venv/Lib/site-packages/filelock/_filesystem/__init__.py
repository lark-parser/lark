"""Filesystem operations shared by lock backends."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from importlib.machinery import ModuleSpec

__spec__ = cast("ModuleSpec", __spec__)

__lazy_modules__ = [f"{__spec__.parent}._exchange", f"{__spec__.parent}._files", f"{__spec__.parent}._ownership"]

import sys

from ._exchange import (
    break_lock_file,
    break_marker_path,
    break_marker_pid,
    exchange_back,
    exchange_names,
    exchange_supported,
    remove_own_file,
    write_break_marker,
)
from ._files import (
    ensure_directory_exists,
    open_into,
    pin_inode,
    raise_on_not_writable_file,
    touch,
    write_all,
    write_at_start,
)
from ._ownership import foreign_owner

if sys.platform == "win32":  # pragma: win32 cover
    from ._windows import (
        DirectoryPinBlockedError,
        cancelling_oplock_wait,
        create_deletable_fd,
        create_exclusive_non_reparse_fd,
        directory_is_private,
        identity_at,
        identity_of_fd,
        is_unlinked,
        make_private_directory,
        mark_delete_disposition,
        open_deletable_for_reading,
        open_for_delete_without_oplock_wait,
        open_non_reparse_fd,
        open_read_without_oplock_wait,
        oplock_wait_cancelled,
        pin_directory,
        pinned,
        rename_open_file,
        unlink_without_oplock_wait,
        unpin_directory,
    )

    # Finalizers can unlink after Python has disabled imports.
    unlink_path = unlink_without_oplock_wait

    __all__ = [
        "DirectoryPinBlockedError",
        "break_lock_file",
        "break_marker_path",
        "break_marker_pid",
        "cancelling_oplock_wait",
        "create_deletable_fd",
        "create_exclusive_non_reparse_fd",
        "directory_is_private",
        "ensure_directory_exists",
        "exchange_back",
        "exchange_names",
        "exchange_supported",
        "foreign_owner",
        "identity_at",
        "identity_of_fd",
        "is_unlinked",
        "make_private_directory",
        "mark_delete_disposition",
        "open_deletable_for_reading",
        "open_for_delete_without_oplock_wait",
        "open_into",
        "open_non_reparse_fd",
        "open_read_without_oplock_wait",
        "oplock_wait_cancelled",
        "pin_directory",
        "pin_inode",
        "pinned",
        "raise_on_not_writable_file",
        "remove_own_file",
        "rename_open_file",
        "touch",
        "unlink_path",
        "unlink_without_oplock_wait",
        "unpin_directory",
        "write_all",
        "write_at_start",
        "write_break_marker",
    ]
else:  # pragma: win32 no cover
    from ._exchange import unlink_path

    __all__ = [
        "break_lock_file",
        "break_marker_path",
        "break_marker_pid",
        "ensure_directory_exists",
        "exchange_back",
        "exchange_names",
        "exchange_supported",
        "foreign_owner",
        "open_into",
        "pin_inode",
        "raise_on_not_writable_file",
        "remove_own_file",
        "touch",
        "unlink_path",
        "write_all",
        "write_at_start",
        "write_break_marker",
    ]
