"""Activation script filtering shared with target interpreters that lack virtualenv."""

from __future__ import annotations

__lazy_modules__ = ["contextlib", "pathlib", "shutil", "tempfile"]

import os
import shutil
from contextlib import suppress
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import SimpleNamespace
    from venv import EnvBuilder

    _Install = Callable[[EnvBuilder, SimpleNamespace, str], None]

_STDLIB_ACTIVATORS: Final[tuple[str, ...]] = (
    "activate",
    "activate.fish",
    "Activate.ps1",
    *(("activate.bat", "deactivate.bat") if os.name == "nt" else ("activate.csh",)),
)


def discard_stdlib_scripts(directory: Path, remove: Callable[[Path], None]) -> None:
    for name in _STDLIB_ACTIVATORS:
        with suppress(FileNotFoundError):
            remove(directory / name)


def vendor_templates(install: _Install) -> _Install:
    def install_scripts(builder: EnvBuilder, context: SimpleNamespace, path: str) -> None:
        # A competing creator can remove a stock script between the stdlib's write and copymode.
        # Feed it only the vendor templates that virtualenv leaves in the environment.
        excluded = {os.path.normcase(name) for name in _STDLIB_ACTIVATORS}
        vendor = []
        for folder, dirs, names in os.walk(path):
            if folder == path:
                dirs[:] = [name for name in dirs if name in {"common", os.name}]
                continue
            directory = Path(folder)
            vendor.extend(
                directory / name
                for name in names
                if directory.parent != Path(path) or os.path.normcase(name) not in excluded
            )
        if vendor:
            with TemporaryDirectory() as stage:
                for template in vendor:
                    dest = Path(stage, template.relative_to(path))
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(template, dest)
                install(builder, context, stage)

    return install_scripts


__all__ = [
    "discard_stdlib_scripts",
    "vendor_templates",
]
