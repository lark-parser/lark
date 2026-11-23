from __future__ import annotations

__lazy_modules__ = ["itertools", "pathlib", "shlex"]

import shlex  # isort: skip # fmt: skip
from itertools import groupby  # isort: skip # fmt: skip
from pathlib import Path  # fmt: skip
from typing import TYPE_CHECKING  # fmt: skip

from virtualenv.activation.via_template import ViaTemplateActivator  # isort: skip # fmt: skip

if TYPE_CHECKING:
    from collections.abc import Iterator

    from virtualenv.create.creator import Creator


class BashActivator(ViaTemplateActivator):  # fmt: skip
    """Generate the ``activate`` script for POSIX Bourne-compatible shells."""

    def templates(self) -> Iterator[str]:
        """The template file names to instantiate.

        :yields: the template file names

        """
        yield "activate.sh"

    def as_name(self, template: str) -> str:
        """The file name of the generated script, the template name without its suffix.

        :param template: the name of the template file

        :returns: the name of the generated script

        """
        return Path(template).stem

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

    @staticmethod
    def quote(string: str) -> str:
        """Quote a value for the generated activation script.

        :param string: the value to quote

        :returns: a shell word that evaluates to the value's UTF-8 bytes

        """
        if string.isascii():
            return shlex.quote(string)

        # Keep source ASCII so a legacy multibyte decoder cannot absorb a quote delimiter.
        parts: list[str] = []
        for is_ascii, group in groupby(string, key=str.isascii):
            chunk = "".join(group)
            if is_ascii:
                parts.append(shlex.quote(chunk))
            else:
                octal = "".join(f"\\0{byte:03o}" for byte in chunk.encode())
                # zsh needs its builtin when no external printf exists.
                parts.append(f"\"$(unset -f printf 2>/dev/null || :; \\printf '%b' '{octal}')\"")
        return "".join(parts)


__all__ = [
    "BashActivator",
]
