"""Extract wheel entries within their target directory."""

from __future__ import annotations

import ntpath
import posixpath
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import zipfile
    from pathlib import Path


def extract_zip(zip_ref: zipfile.ZipFile, target_dir: Path) -> None:
    # A tampered wheel entry must not escape its extraction directory.
    base = target_dir.resolve()
    for info in zip_ref.infolist():
        name = info.filename
        if name.startswith(("/", "\\")) or ntpath.isabs(name) or posixpath.isabs(name):
            msg = f"refusing to extract absolute path entry from wheel: {name!r}"
            raise RuntimeError(msg)
        candidate = (base / name).resolve()
        try:
            candidate.relative_to(base)
        except ValueError as exc:
            msg = f"refusing to extract entry escaping target directory: {name!r}"
            raise RuntimeError(msg) from exc
    zip_ref.extractall(str(target_dir))


__all__ = [
    "extract_zip",
]
