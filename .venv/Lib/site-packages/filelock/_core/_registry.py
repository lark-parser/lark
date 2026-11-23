"""Canonical path keys and per-thread lock counts."""

from __future__ import annotations

import os
import sys
from threading import local
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Callable, Hashable


# Windows realpath opens directories without delete sharing, which can stall a concurrent release.
_RESOLVE_DIR: Final[Callable[[str], str]] = os.path.abspath if sys.platform == "win32" else os.path.realpath


class _ThreadLocalRegistry(local):
    def __init__(self) -> None:
        super().__init__()
        self.held: dict[Hashable, int] = {}


REGISTRY: Final[_ThreadLocalRegistry] = _ThreadLocalRegistry()


def path_key(path: str) -> str:
    # Windows directories can have case-sensitive names even when the drive prefix ignores case.
    drive, tail = os.path.splitdrive(path)
    return drive.lower() + tail


def canonical(path: str | os.PathLike[str]) -> str:
    # Resolving the final component would give a rejected symlink the same registry key as its target.
    parent, name = os.path.split(os.fspath(path))
    return os.path.join(_RESOLVE_DIR(parent or os.curdir), name)  # ruff:ignore[os-path-join]  # preserve string paths


__all__ = [
    "REGISTRY",
    "canonical",
    "path_key",
]
