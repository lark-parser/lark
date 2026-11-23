"""
Internal hook annotation, representation and calling machinery.

This module re-exports symbols from the role-specific modules for
backward compatibility.
"""

from __future__ import annotations

from ._caller import _HookCaller
from ._caller import _HookExec
from ._caller import _HookRelay
from ._caller import _SubsetHookCaller
from ._caller import HookCaller
from ._caller import HookRelay
from ._config import HookimplOpts
from ._config import HookspecOpts
from ._config import normalize_hookimpl_opts
from ._decorators import _Namespace
from ._decorators import HookimplMarker
from ._decorators import HookSpec
from ._decorators import HookspecMarker
from ._decorators import varnames
from ._impl import _HookImplFunction
from ._impl import _Plugin
from ._impl import HookImpl


__all__ = [
    "HookCaller",
    "HookImpl",
    "HookRelay",
    "HookSpec",
    "HookimplMarker",
    "HookimplOpts",
    "HookspecMarker",
    "HookspecOpts",
    "_HookCaller",
    "_HookExec",
    "_HookImplFunction",
    "_HookRelay",
    "_Namespace",
    "_Plugin",
    "_SubsetHookCaller",
    "normalize_hookimpl_opts",
    "varnames",
]
