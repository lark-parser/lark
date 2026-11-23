"""The installed distribution version."""

from __future__ import annotations

from importlib.metadata import version

#: the installed distribution version
__version__ = version("python-discovery")
