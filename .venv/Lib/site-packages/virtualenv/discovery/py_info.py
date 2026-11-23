"""Backward-compatibility re-export — use ``python_discovery.PythonInfo`` directly."""

from __future__ import annotations

__lazy_modules__ = ["python_discovery"]

from python_discovery import PythonInfo

__all__ = [
    "PythonInfo",
]
