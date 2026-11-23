"""
Call loop machinery.

This module re-exports the execution engine for backward compatibility.
Prefer importing from :mod:`pluggy._execution`.
"""

from __future__ import annotations

from ._execution import _multicall
from ._execution import _raise_wrapfail
from ._execution import _warn_teardown_exception
from ._execution import run_old_style_hookwrapper
from ._execution import Teardown


__all__ = [
    "Teardown",
    "_multicall",
    "_raise_wrapfail",
    "_warn_teardown_exception",
    "run_old_style_hookwrapper",
]
