"""Android app folder discovery."""

from __future__ import annotations

__lazy_modules__ = ["contextlib"]

import re
import sys
from contextlib import suppress
from functools import lru_cache

TYPE_CHECKING = False
if TYPE_CHECKING:
    from typing import Final


@lru_cache(maxsize=1)
def android_folder() -> str | None:
    result = None
    with suppress(ImportError):
        from jnius import JavaException, autoclass  # ruff:ignore[import-outside-top-level]  # jnius exists only on Android  # ty: ignore[import-not-found]

        with suppress(JavaException):
            # A python-for-android service runs in its own process, where the activity is null.
            if (context := autoclass("org.kivy.android.PythonActivity").mActivity) is None:
                context = autoclass("org.kivy.android.PythonService").mService
            if context is not None:
                result = context.getFilesDir().getParentFile().getAbsolutePath()
    if result is None:
        # This path only works for apps in regular internal storage.
        for path in sys.path:
            if match := _ANDROID_FOLDER_PATTERN.match(path):
                result = match["folder"]
                break
    if result is None:
        for path in sys.path:
            if match := _ANDROID_FOLDER_PATTERN_2.match(path):
                result = match["folder"]
                break
    return result


_ANDROID_FOLDER_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"""
            (?P<folder>
                /data/(?:data|user/\d+)  # internal storage of the primary user or of user N
                /[^/]+                   # package name, one path segment
            )
            /files(?=/|\Z)               # the files directory the interpreter runs from
            """,
    re.VERBOSE,
)

_ANDROID_FOLDER_PATTERN_2: Final[re.Pattern[str]] = re.compile(
    r"""
            (?P<folder>
                /mnt/expand/[a-fA-F0-9-]{36}  # adopted storage volume, named by its UUID
                /(?:data|user/\d+)             # the primary user or user N
                /[^/]+                         # package name, one path segment
            )
            /files(?=/|\Z)                     # the files directory the interpreter runs from
            """,
    re.VERBOSE,
)


__all__ = [
    "android_folder",
]
