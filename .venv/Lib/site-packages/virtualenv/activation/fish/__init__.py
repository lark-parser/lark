from __future__ import annotations

import re  # isort: skip # fmt: skip
from typing import TYPE_CHECKING, Final  # isort: skip # fmt: skip

from virtualenv.activation.via_template import ViaTemplateActivator  # isort: skip # fmt: skip

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from virtualenv.create.creator import Creator


_ESCAPED_PATTERN: Final[re.Pattern[str]] = re.compile(r"[\\']")  # fmt: skip


class FishActivator(ViaTemplateActivator):  # fmt: skip
    """Generate the ``activate.fish`` script for fish."""

    def templates(self) -> Iterator[str]:
        """The template file names to instantiate.

        :yields: the template file names

        """
        yield "activate.fish"

    @staticmethod
    def quote(string: str) -> str:
        """Quote the value for fish, wrapping it in single quotes and escaping backslashes and single quotes.

        :param string: the value to quote

        :returns: the quoted value

        """
        # Keep escapes beside ASCII quotes so legacy decoders cannot absorb them into a preceding multibyte character.
        escaped = _ESCAPED_PATTERN.sub(lambda match: f"'\\{match.group()}'", string)
        return f"'{escaped}'"

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


__all__ = [
    "FishActivator",
]
