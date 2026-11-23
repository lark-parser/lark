from __future__ import annotations

__lazy_modules__ = [
    "collections",
    "virtualenv.util.path",
    "virtualenv.util.text",
]

import logging
import os
from collections import OrderedDict
from typing import TYPE_CHECKING, Final

from virtualenv.util.path import write_file
from virtualenv.util.text import collapse_line_boundaries

if TYPE_CHECKING:
    from pathlib import Path

LOGGER: Final[logging.Logger] = logging.getLogger(__name__)  # simplint: ignore[module-variable-prefix]  # existing name

# a plain value such as 3.14 or true would otherwise turn into a path whenever the working directory has an entry so
# named
_PATH_KEYS: Final[frozenset[str]] = frozenset({
    "home",
    "executable",
    "base-prefix",
    "base-exec-prefix",
    "base-executable",
    "venvlauncher_command",
})


class PyEnvCfg:
    """The ``pyvenv.cfg`` file of an environment, read into ordered key-value pairs.

    :param content: the key-value pairs in file order
    :param path: the location of the file

    """

    def __init__(self, content: OrderedDict[str, str], path: Path) -> None:
        self.content = content
        self.path = path

    @classmethod
    def from_folder(cls, folder: Path) -> PyEnvCfg:
        """Load the ``pyvenv.cfg`` of the environment in the given folder.

        :param folder: the environment folder

        :returns: the parsed configuration, empty when the file does not exist

        """
        return cls.from_file(folder / "pyvenv.cfg")

    @classmethod
    def from_file(cls, path: Path) -> PyEnvCfg:
        """Load the ``pyvenv.cfg`` at the given path.

        :param path: the location of the file

        :returns: the parsed configuration, empty when the file does not exist

        """
        return PyEnvCfg(cls._read_values(path) if path.exists() else OrderedDict(), path)

    @staticmethod
    def _read_values(path: Path) -> OrderedDict[str, str]:
        _validate_path(path)
        content = OrderedDict()
        for line in path.read_text(encoding="utf-8").splitlines():
            key, separator, value = line.partition("=")
            if not separator or (key := key.strip()).startswith("#"):
                continue
            value = value.strip()
            if len(value) > 1 and value[0] in {"'", '"'} and value[0] == value[-1]:
                value = value[1:-1]
            content[key] = value
        return content

    def __setitem__(self, key: str, value: str) -> None:
        self.content[key] = value

    def __getitem__(self, key: str) -> str:
        return self.content[key]

    def __contains__(self, item: str) -> bool:
        return item in self.content

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(path={self.path})"

    def write(self) -> None:
        """Write the key-value pairs to the file, quoting the prompt and absolutizing existing paths.

        :raises ValueError: when a CPython configuration would be too large to read

        """
        _validate_path(self.path)
        LOGGER.debug("write %s", self.path)
        write_file(self.path, self.serialize())

    def serialize(self) -> bytes:
        """Build the configuration before writing it.

        :returns: the UTF-8 configuration

        :raises ValueError: when a CPython configuration would be too large to read

        """
        paths = validated_paths(self.content, self.path)
        text = ""
        for key, value in self.content.items():
            normalized_value = f'"{value}"' if key == "prompt" and value else paths.get(key, value)
            line = f"{collapse_line_boundaries(key)} = {collapse_line_boundaries(normalized_value)}"
            LOGGER.debug("\t%r", line)
            text += line
            text += "\n"
        encoded: Final[bytes] = text.encode("utf-8")
        cpython_config_limit: Final[int] = 32_768
        if (
            len(encoded) >= cpython_config_limit
            and self.content.get("implementation") == "CPython"
            and tuple(map(int, self.content.get("python-version", "3.11").split("."))) >= (3, 11)
        ):
            msg: Final[str] = "pyvenv.cfg must be smaller than 32 KiB for CPython to start"
            raise ValueError(msg)
        return encoded

    def refresh(self) -> OrderedDict[str, str]:
        """Re-read the key-value pairs from the file, discarding in-memory changes.

        :returns: the key-value pairs read from the file

        """
        self.content = self._read_values(self.path)
        return self.content

    def update(self, other: dict[str, str]) -> PyEnvCfg:
        """Merge the given pairs into the configuration.

        :param other: the key-value pairs to add or overwrite

        :returns: this configuration, to allow chaining

        """
        self.content.update(other)
        return self


def _validate_path(path: Path) -> None:
    if path.exists() and not path.is_file():
        msg = f"configuration path is not a regular file: {path}"
        raise ValueError(msg)


def validated_paths(content: OrderedDict[str, str], path: Path) -> dict[str, str]:
    """Normalize path values for the configuration.

    :param content: the key-value pairs to check
    :param path: the configuration path used in errors

    :returns: normalized path values by key

    :raises ValueError: when recording would change a path

    """
    paths = {}
    for key, value in content.items():
        if key not in _PATH_KEYS:
            continue
        # abspath rather than realpath keeps symlinked prefixes intact, as venv does (#2770)
        normalized_value = os.path.abspath(value) if os.path.exists(value) else value
        if collapse_line_boundaries(normalized_value).strip() != normalized_value:
            msg = f"cannot record {key} path {normalized_value!r} in {path}"
            raise ValueError(msg)
        paths[key] = normalized_value
    return paths


__all__ = [
    "PyEnvCfg",
    "validated_paths",
]
