from __future__ import annotations

__lazy_modules__ = [
    f"{__spec__.parent}.bash",  # ty: ignore[missing-union-attribute]  # imported modules have a spec
    f"{__spec__.parent}.batch",  # ty: ignore[missing-union-attribute]  # imported modules have a spec
    f"{__spec__.parent}.cshell",  # ty: ignore[missing-union-attribute]  # imported modules have a spec
    f"{__spec__.parent}.fish",  # ty: ignore[missing-union-attribute]  # imported modules have a spec
    f"{__spec__.parent}.nushell",  # ty: ignore[missing-union-attribute]  # imported modules have a spec
    f"{__spec__.parent}.powershell",  # ty: ignore[missing-union-attribute]  # imported modules have a spec
    f"{__spec__.parent}.python",  # ty: ignore[missing-union-attribute]  # imported modules have a spec
    f"{__spec__.parent}.xonsh",  # ty: ignore[missing-union-attribute]  # imported modules have a spec
]

from .bash import BashActivator
from .batch import BatchActivator
from .cshell import CShellActivator
from .fish import FishActivator
from .nushell import NushellActivator
from .powershell import PowerShellActivator
from .python import PythonActivator
from .xonsh import XonshActivator

__all__ = [
    "BashActivator",
    "BatchActivator",
    "CShellActivator",
    "FishActivator",
    "NushellActivator",
    "PowerShellActivator",
    "PythonActivator",
    "XonshActivator",
]
