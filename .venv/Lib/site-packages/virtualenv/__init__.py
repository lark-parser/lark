from __future__ import annotations

__lazy_modules__ = [
    f"{__spec__.parent}.run",  # ty: ignore[missing-union-attribute]  # imported modules have a spec
    f"{__spec__.parent}.version",  # ty: ignore[missing-union-attribute]  # imported modules have a spec
]

from .run import cli_run, session_via_cli
from .version import __version__

__all__ = [
    "__version__",
    "cli_run",
    "session_via_cli",
]
