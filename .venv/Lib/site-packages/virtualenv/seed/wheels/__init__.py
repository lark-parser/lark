from __future__ import annotations

__lazy_modules__ = [
    f"{__spec__.parent}.acquire",  # ty: ignore[missing-union-attribute]  # imported modules have a spec
    f"{__spec__.parent}.util",  # ty: ignore[missing-union-attribute]  # imported modules have a spec
]

from .acquire import get_wheel, pip_wheel_env_run
from .util import Version, Wheel

__all__ = [
    "Version",
    "Wheel",
    "get_wheel",
    "pip_wheel_env_run",
]
