"""Windows file handles, directory pins, and oplock-aware operations."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from importlib.machinery import ModuleSpec

__spec__ = cast("ModuleSpec", __spec__)

__lazy_modules__ = [f"{__spec__.parent}._directories", f"{__spec__.parent}._handles"]

import sys

if sys.platform == "win32":  # pragma: win32 cover
    from ._directories import (
        DirectoryPinBlockedError,
        directory_is_private,
        make_private_directory,
        pin_directory,
        pinned,
        unpin_directory,
    )
    from ._handles import (
        create_deletable_fd,
        identity_at,
        identity_of_fd,
        is_unlinked,
        mark_delete_disposition,
        open_deletable_for_reading,
        open_non_reparse_fd,
        rename_open_file,
    )
    from ._oplocks import (
        cancelling_oplock_wait,
        create_exclusive_non_reparse_fd,
        open_for_delete_without_oplock_wait,
        open_read_without_oplock_wait,
        oplock_wait_cancelled,
        unlink_without_oplock_wait,
    )

    __all__ = [
        "DirectoryPinBlockedError",
        "cancelling_oplock_wait",
        "create_deletable_fd",
        "create_exclusive_non_reparse_fd",
        "directory_is_private",
        "identity_at",
        "identity_of_fd",
        "is_unlinked",
        "make_private_directory",
        "mark_delete_disposition",
        "open_deletable_for_reading",
        "open_for_delete_without_oplock_wait",
        "open_non_reparse_fd",
        "open_read_without_oplock_wait",
        "oplock_wait_cancelled",
        "pin_directory",
        "pinned",
        "rename_open_file",
        "unlink_without_oplock_wait",
        "unpin_directory",
    ]
else:  # pragma: win32 no cover
    __all__ = []
