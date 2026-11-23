"""pytest plugin that provides the ``platformdirs_isolated`` fixture."""

from __future__ import annotations

import pytest

TYPE_CHECKING = False  #: :data:`typing.TYPE_CHECKING` without importing :mod:`typing` at runtime
if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


@pytest.fixture
def platformdirs_isolated(  # simplint: ignore[imported-fixture]  # public pytest11 fixture
    tmp_path: Path,
) -> Iterator[Path]:
    """Redirect every platformdirs directory under ``tmp_path`` with :func:`~platformdirs.testing.isolated_dirs`.

    :param tmp_path: the directory that holds the redirected directories.

    :yields: the isolation root, ``tmp_path``

    """
    # pytest imports every installed pytest11 plugin at startup, so load the helper only for tests that ask for it.
    from .testing import isolated_dirs  # ruff:ignore[import-outside-top-level]

    with isolated_dirs(tmp_path) as root:
        yield root


__all__ = [
    "platformdirs_isolated",
]
