from __future__ import annotations

__lazy_modules__ = ["collections"]

import os  # isort: skip # fmt: skip
from collections import OrderedDict  # isort: skip # fmt: skip
from typing import TYPE_CHECKING  # isort: skip # fmt: skip

from virtualenv.activation.via_template import ViaTemplateActivator  # isort: skip # fmt: skip

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from virtualenv.create.creator import Creator


class PythonActivator(ViaTemplateActivator):  # fmt: skip
    """Generate the ``activate_this.py`` script that a Python program runs to activate the environment."""

    def templates(self) -> Iterator[str]:
        """The template file names to instantiate.

        :yields: the template file names

        """
        yield "activate_this.py"

    @staticmethod
    def quote(string: str) -> str:
        """Quote the value as a Python literal, ASCII only.

        :param string: the value to quote

        :returns: the ``ascii`` representation of the value

        """
        return ascii(string)

    def replacements(self, creator: Creator, dest_folder: Path) -> dict[str, str]:
        """The raw placeholder values, adding the library folders and the path decoding hook.

        :param creator: the creator of the environment
        :param dest_folder: the folder the scripts are written into

        :returns: the placeholder names mapped to their values

        """
        replacements = super().replacements(creator, dest_folder)
        lib_folders = OrderedDict((os.path.relpath(str(i), str(dest_folder)), None) for i in creator.libs)
        lib_folders = os.pathsep.join(lib_folders.keys())
        replacements.update(
            {
                "__LIB_FOLDERS__": lib_folders,
                "__DECODE_PATH__": "",
            },
        )
        return replacements


__all__ = [
    "PythonActivator",
]
