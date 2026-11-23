from __future__ import annotations

__lazy_modules__ = ["logging"]

import logging  # isort: skip # fmt: skip
import os  # isort: skip # fmt: skip
import re  # isort: skip # fmt: skip
from typing import TYPE_CHECKING, Final  # isort: skip # fmt: skip

from virtualenv.activation.via_template import ViaTemplateActivator  # isort: skip # fmt: skip

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from virtualenv.create.creator import Creator


_GENERATE_PATTERN: Final[re.Pattern[str]] = re.compile(r"\$(?:\w+|{)|=~")  # fmt: skip
_UNSAFE_LITERAL_PATTERN: Final[re.Pattern[str]] = re.compile(r"[^ -~]|['\\+~%]")


class XonshActivator(ViaTemplateActivator):  # fmt: skip
    """Generate the ``activate.xsh`` script for xonsh."""

    def generate(self, creator: Creator) -> list[Path]:
        """Generate the script, or remove it when the destination holds xonsh path expansion syntax.

        :param creator: the creator of the environment

        :returns: the paths of the generated scripts, empty when the destination is skipped

        """
        if _GENERATE_PATTERN.search(str(creator.dest)):
            logging.getLogger(__name__).warning(
                "skipping xonsh activation script: destination %s contains path expansion syntax", creator.dest
            )
            (creator.bin_dir / "activate.xsh").unlink(missing_ok=True)
            return []
        return super().generate(creator)

    def templates(self) -> Iterator[str]:
        """The template file names to instantiate.

        :yields: the template file names

        """
        yield "activate.xsh"

    @staticmethod
    def quote(string: str) -> str:
        """Keep literals independent of the encoding xonsh uses to read the script.

        :param string: the value to quote

        :returns: an ASCII-only expression for the string

        """
        if _UNSAFE_LITERAL_PATTERN.search(string):
            return f"''.join(__import__('builtins').map(__import__('builtins').chr, {tuple(map(ord, string))!r}))"
        return ascii(string)

    def replacements(self, creator: Creator, dest_folder: Path) -> dict[str, str]:
        """The raw placeholder values, including the Tcl and Tk library paths.

        :param creator: the creator of the environment
        :param dest_folder: the folder the scripts are written into

        :returns: the placeholder names mapped to their values

        """
        data = super().replacements(creator, dest_folder)
        data.update({
            "__TCL_LIBRARY__": self._library_path(creator, "tcl_lib", b"TCL_LIBRARY"),
            "__TK_LIBRARY__": self._library_path(creator, "tk_lib", b"TK_LIBRARY"),
        })
        return data

    def substitutions(self, replacements: dict[str, str], creator: Creator) -> dict[str, str]:
        """Embed non-ASCII POSIX paths as bytes for the script to decode with the active filesystem codec.

        :param replacements: the raw placeholder values
        :param creator: the creator of the environment

        :returns: placeholder values safe for the active filesystem codec

        """
        data = super().substitutions(replacements, creator)
        for name in ("__VIRTUAL_ENV__", "__TCL_LIBRARY__", "__TK_LIBRARY__"):
            if os.name != "nt" and not replacements[name].isascii():
                data[name] = f"__import__('builtins').bytes.fromhex('{replacements[name].encode('utf-8').hex()}')"
        return data


__all__ = [
    "XonshActivator",
]
