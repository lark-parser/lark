"""Windows-specific Python discovery via PEP 514 registry entries."""

from __future__ import annotations

from ._cancel_io import stop_query_reader
from ._propose import propose_interpreters

__all__ = [
    "propose_interpreters",
    "stop_query_reader",
]
