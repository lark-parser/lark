from __future__ import annotations

from typing import TYPE_CHECKING  # isort: skip # fmt: skip

from virtualenv.activation.via_template import ViaTemplateActivator  # isort: skip # fmt: skip

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from virtualenv.create.creator import Creator


class NushellActivator(ViaTemplateActivator):  # fmt: skip
    """Generate the ``activate.nu`` script for Nushell."""

    def templates(self) -> Iterator[str]:
        """The template file names to instantiate.

        :yields: the template file names

        """
        yield "activate.nu"

    @staticmethod
    def quote(string: str) -> str:
        """Nushell supports raw strings like: r###'this is a string'###.

        https://github.com/nushell/nushell.github.io/blob/main/book/working_with_strings.md

        This method finds the maximum continuous sharps in the string and then quote it with an extra sharp.

        :param string: the value to quote

        :returns: the string wrapped in a raw string literal with enough sharps to not clash with its content

        """
        max_sharps = 0
        current_sharps = 0
        for char in string:
            if char == "#":
                current_sharps += 1
                max_sharps = max(current_sharps, max_sharps)
            else:
                current_sharps = 0
        wrapping = "#" * (max_sharps + 1)
        return f"r{wrapping}'{string}'{wrapping}"

    # the replacement hook signature, nushell needs neither argument
    def replacements(self, creator: Creator, dest_folder: Path) -> dict[str, str]:  # ruff:ignore[unused-method-argument]
        """The raw placeholder values, including the Tcl and Tk library paths.

        :param creator: the creator of the environment
        :param dest_folder: the folder the scripts are written into

        :returns: the placeholder names mapped to their values

        """
        return {
            "__VIRTUAL_PROMPT__": "" if self.flag_prompt is None else self.flag_prompt,
            "__VIRTUAL_ENV__": str(creator.dest),
            "__VIRTUAL_NAME__": creator.env_name,
            "__BIN_NAME__": str(creator.bin_dir.relative_to(creator.dest)),
            "__TCL_LIBRARY__": self._library_path(creator, "tcl_lib", b"TCL_LIBRARY"),
            "__TK_LIBRARY__": self._library_path(creator, "tk_lib", b"TK_LIBRARY"),
        }


__all__ = [
    "NushellActivator",
]
