from __future__ import annotations

__lazy_modules__ = ["pathlib"]

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from python_discovery import PythonInfo

    from .api import ViaGlobalRefMeta


def handle_store_python(meta: ViaGlobalRefMeta, interpreter: PythonInfo) -> ViaGlobalRefMeta:
    """Mark the metadata as unable to symlink when the interpreter is a Windows Store Python.

    :param meta: the capability metadata to update
    :param interpreter: the interpreter the environment is created from

    :returns: the same metadata, updated in place

    """
    if is_store_python(interpreter):
        meta.symlink_error = "Windows Store Python does not support virtual environments via symlink"
    return meta


def is_store_python(interpreter: PythonInfo) -> bool:
    """Check whether the interpreter is installed from the Windows Store.

    :param interpreter: the interpreter to check

    :returns: ``True`` when the executable lives in a Windows Store package folder

    """
    parts = Path(interpreter.system_exe).parts
    return (
        # a Windows Store path has at least four parts, so shorter paths cannot match
        len(parts) > 4  # ruff:ignore[magic-value-comparison]
        and parts[-4] == "Microsoft"
        and parts[-3] == "WindowsApps"
        and parts[-2].startswith("PythonSoftwareFoundation.Python.3.")
        and parts[-1].startswith("python")
    )


__all__ = [
    "handle_store_python",
    "is_store_python",
]
