"""Compatibility helpers."""

from __future__ import annotations

from typing import Any
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    import importlib.metadata


class DistFacade:
    """Facade providing pkg_resources.Distribution-like interface.

    This class wraps importlib.metadata.Distribution to provide a
    compatibility layer for code expecting the legacy pkg_resources API.
    The primary difference is the ``project_name`` attribute which
    pkg_resources provided but importlib.metadata.Distribution does not.
    """

    __slots__ = ("_dist",)

    def __init__(self, dist: importlib.metadata.Distribution) -> None:
        self._dist = dist

    @property
    def project_name(self) -> str:
        """Get the project name (for pkg_resources compatibility).

        This is equivalent to dist.metadata["name"] but matches the
        pkg_resources.Distribution.project_name attribute.
        """
        name: str = self.metadata["name"]
        return name

    def __getattr__(self, attr: str) -> Any:
        """Delegate all other attributes to the wrapped Distribution."""
        return getattr(self._dist, attr)

    def __dir__(self) -> list[str]:
        """List available attributes including facade additions."""
        return sorted(dir(self._dist) + ["_dist", "project_name"])
