from __future__ import annotations

__lazy_modules__ = [
    f"{__spec__.parent}._permission",  # ty: ignore[missing-union-attribute]  # imported modules have a spec
    f"{__spec__.parent}._sync",  # ty: ignore[missing-union-attribute]  # imported modules have a spec
    f"{__spec__.parent}._win",  # ty: ignore[missing-union-attribute]  # imported modules have a spec
]

from ._permission import make_exe, make_tree_read_only, owner_executable_mode, set_tree
from ._sync import (
    copy,
    ensure_dir,
    ensure_within,
    remove_file,
    safe_delete,
    safe_delete_read_only,
    symlink,
    write_file,
)
from ._win import get_short_path_name

__all__ = [
    "copy",
    "ensure_dir",
    "ensure_within",
    "get_short_path_name",
    "make_exe",
    "make_tree_read_only",
    "owner_executable_mode",
    "remove_file",
    "safe_delete",
    "safe_delete_read_only",
    "set_tree",
    "symlink",
    "write_file",
]
