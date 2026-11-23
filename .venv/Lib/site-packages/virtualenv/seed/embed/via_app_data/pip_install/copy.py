from __future__ import annotations

__lazy_modules__ = [
    "pathlib",
    "virtualenv.util.path",
]

import os
from pathlib import Path
from typing import TYPE_CHECKING

from virtualenv.util.path import copy

from .base import PipInstall

if TYPE_CHECKING:
    from collections.abc import Generator


class CopyPipInstall(PipInstall):
    """Install a seed package by copying its image files into the environment."""

    def _sync(self, src: Path, dst: Path) -> None:
        copy(src, dst)

    def _generate_new_files(self, folder: Path, dist_info: Path) -> set[Path]:
        # create the pyc files
        new_files = super()._generate_new_files(folder, dist_info)
        new_files.update(self._cache_files(folder))
        return new_files

    def _cache_files(self, folder: Path) -> Generator[Path, None, None]:
        version = self._creator.interpreter.version_info
        py_c_ext = f".{self._creator.interpreter.implementation.lower()}-{version.major}{version.minor}.pyc"
        for root, dirs, files in os.walk(str(folder), topdown=True):
            root_path = Path(root)
            for name in files:
                if name.endswith(".py"):
                    yield root_path / f"{name[:-3]}{py_c_ext}"
            for name in dirs:
                yield root_path / name / "__pycache__"

    def _fix_records(self, folder: Path, dist_info: Path, extra_record_data: set[Path]) -> None:
        extra_record_data_str = self._records_text(folder, extra_record_data)
        with (dist_info / "RECORD").open("a+b") as file_handler:
            if file_handler.tell():
                file_handler.seek(-1, os.SEEK_END)
                if file_handler.read(1) != b"\n":
                    file_handler.write(b"\n")
            file_handler.write(extra_record_data_str.encode("utf-8"))


__all__ = [
    "CopyPipInstall",
]
