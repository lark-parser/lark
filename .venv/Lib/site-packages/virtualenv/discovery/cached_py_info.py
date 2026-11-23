"""Backward-compatibility re-export — use ``python_discovery`` directly."""

from __future__ import annotations

__lazy_modules__ = ["python_discovery._cached_py_info"]

# python_discovery exposes its cache helpers only from the private module
from python_discovery._cached_py_info import clear, from_exe  # ruff:ignore[import-private-name]  # simplint: ignore[private-import-path]  # legacy signatures

__all__ = [
    "clear",
    "from_exe",
]
