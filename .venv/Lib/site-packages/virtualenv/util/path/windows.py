from __future__ import annotations

import os


def windows_extended_path(path: str) -> str:
    """Get an absolute Windows path for operations beyond MAX_PATH.

    :param path: the Windows path to normalize

    :returns: the path with an extended-length prefix

    """
    path = os.path.abspath(path)
    if path.startswith(("\\\\?\\", "\\\\.\\")):
        return path
    return f"\\\\?\\UNC\\{path[2:]}" if path.startswith("\\\\") else f"\\\\?\\{path}"


__all__ = [
    "windows_extended_path",
]
