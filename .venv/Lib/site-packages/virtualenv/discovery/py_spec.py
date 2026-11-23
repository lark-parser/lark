"""Backward-compatibility re-export — use ``python_discovery.PythonSpec`` directly."""

from __future__ import annotations

__lazy_modules__ = ["python_discovery"]

from python_discovery import PythonSpec

__all__ = [
    "PythonSpec",
]
