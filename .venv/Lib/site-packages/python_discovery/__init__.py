"""Self-contained Python interpreter discovery."""

from __future__ import annotations

from ._about import __version__
from ._cache import ContentStore, DiskCache, PyInfoCache
from ._discovery import get_interpreter, iter_interpreters
from ._py_info import KNOWN_ARCHITECTURES, MarkerEnvironment, PythonInfo, normalize_isa
from ._py_spec import KNOWN_IMPLEMENTATIONS, PythonSpec
from ._specifier import SimpleSpecifier, SimpleSpecifierSet, SimpleVersion

__all__ = [
    "KNOWN_ARCHITECTURES",
    "KNOWN_IMPLEMENTATIONS",
    "ContentStore",
    "DiskCache",
    "MarkerEnvironment",
    "PyInfoCache",
    "PythonInfo",
    "PythonSpec",
    "SimpleSpecifier",
    "SimpleSpecifierSet",
    "SimpleVersion",
    "__version__",
    "get_interpreter",
    "iter_interpreters",
    "normalize_isa",
]
