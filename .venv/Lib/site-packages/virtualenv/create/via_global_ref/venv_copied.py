from __future__ import annotations

import os
from sys import getfilesystemencoding
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from pathlib import Path

    from python_discovery import PythonInfo


def remove_copied_interpreters(bin_dir: Path, interpreter: PythonInfo) -> None:
    """Remove copied interpreter files before the standard-library creator replaces them.

    :param bin_dir: the environment's script directory
    :param interpreter: the host interpreter to copy

    """
    if os.name != "posix":
        return
    interpreter_names = {
        "python",
        f"python{interpreter.version_info.major}",
        f"python{interpreter.version_info.major}.{interpreter.version_info.minor}",
    }
    # CPython 3.14 adds the pi alias on UTF-8 filesystems.
    if (interpreter.version_info.major, interpreter.version_info.minor) == (
        3,
        14,
    ) and getfilesystemencoding() == "utf-8":
        interpreter_names.add("𝜋thon")
    if interpreter.implementation == "PyPy":
        library: Final[str] = f"libpypy{interpreter.version_info.major}.{interpreter.version_info.minor}-c"
        interpreter_names.update({"pypy", "pypy3", f"{library}.so", f"{library}.dylib"})
    for path in bin_dir.iterdir():
        if path.name in interpreter_names and path.is_file():
            path.unlink()


__all__ = [
    "remove_copied_interpreters",
]
