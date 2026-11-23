from __future__ import annotations

__lazy_modules__ = [
    "pathlib",
    "shutil",
    "typing",
    "uuid",
    "virtualenv.info",
    "virtualenv.util.path.windows",
    "zipfile",
]

import logging
import os
import shutil
import zipfile
from pathlib import Path
from typing import Final
from uuid import uuid4

from virtualenv.info import ROOT
from virtualenv.util.path.windows import windows_extended_path

LOGGER: Final[logging.Logger] = logging.getLogger(__name__)  # simplint: ignore[module-variable-prefix]  # existing name


def read(full_path: str | Path) -> str:
    """Read a file that ships inside the zipapp archive, decoded as UTF-8.

    :param full_path: the path of the file, which must be within the archive root

    :returns: the text of the file

    :raises RuntimeError: when the path is not within the archive root

    """
    with zipfile.ZipFile(ROOT, "r") as zip_file, zip_file.open(_get_path_within_zip(full_path)) as file_handler:
        return file_handler.read().decode("utf-8")


def _get_path_within_zip(full_path: str | Path) -> str:
    # Use Path.relative_to so symlinks and ``..`` segments cannot slip through a string ``startswith`` check. The zipapp
    # root is a real file we own so ``resolve`` is safe; anything that does not resolve under ROOT is a bug or an
    # attempt to escape the archive and we refuse it.
    resolved = Path(full_path).resolve()
    root = Path(ROOT).resolve()
    try:
        relative = resolved.relative_to(root)
    except ValueError as exc:
        msg = f"full_path={resolved} should be within ROOT={root}"
        raise RuntimeError(msg) from exc
    # Zip entries always use forward slashes regardless of platform.
    return relative.as_posix()


def extract(full_path: str | Path, dest: Path) -> None:
    """Extract a file from the zipapp archive to the destination, keeping the destination name.

    :param full_path: the path of the file, which must be within the archive root
    :param dest: the destination file

    """
    LOGGER.debug("extract %s to %s", full_path, dest)
    sub_file = _get_path_within_zip(full_path)
    with zipfile.ZipFile(ROOT, "r") as zip_file:
        info = zip_file.getinfo(sub_file)
        if os.name == "nt":
            dest = Path(windows_extended_path(str(dest)))
        dest.parent.mkdir(parents=True, exist_ok=True)
        temp = dest.with_name(f".{dest.name}.{uuid4().hex}.tmp")
        output = temp.open("xb")
        try:
            with output, zip_file.open(info) as source:
                shutil.copyfileobj(source, output)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temp, dest)
        finally:
            temp.unlink(missing_ok=True)


__all__ = [
    "extract",
    "read",
]
