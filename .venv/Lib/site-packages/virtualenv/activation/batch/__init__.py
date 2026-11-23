from __future__ import annotations

__lazy_modules__ = ["virtualenv.util.text"]

import logging  # isort: skip # fmt: skip
import os  # isort: skip # fmt: skip
from types import MappingProxyType  # isort: skip # fmt: skip
from typing import TYPE_CHECKING, Final  # isort: skip # fmt: skip

from virtualenv.activation.via_template import ViaTemplateActivator, read_binary  # isort: skip # fmt: skip
from virtualenv.util.text import collapse_line_boundaries  # isort: skip # fmt: skip

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from python_discovery import PythonInfo

    from virtualenv.create.creator import Creator

#: Logs the reasons a batch activation script is skipped.
LOGGER: Final[logging.Logger] = logging.getLogger(__name__)  # simplint: ignore[module-variable-prefix]  # existing API  # fmt: skip

# cmd.exe's own command-line parser looks for these regardless of surrounding quotes: confirmed on a
# real Windows runner that `@set "VAR=x & cmd"` still runs `cmd` as a second statement even though the
# whole VAR=value expression is quoted. `(` and `)` are not in this set - confirmed on the same runner
# that `@set "VAR=C:\Program Files (x86)\..."` round-trips unchanged, since parentheses are only special
# to cmd.exe as block delimiters in control-flow syntax (if/for), not as bare characters in a value.
#
# `!` is only live when the caller already has delayed expansion enabled (`setlocal enabledelayedexpansion`,
# `cmd /V:ON`) - not cmd.exe's default, but confirmed on a real runner that a prompt like `foo!SECRET!`
# then substitutes the actual value of an existing SECRET variable into the prompt, so it is neutered
# unconditionally rather than only when that mode happens to be on. cmd.exe stops reading a line at Ctrl-Z
# (0x1A) - confirmed on a real runner that `@set "VAR=a<Ctrl-Z>b"` sets `a` and then runs `b"` as the next command.
_CMD_OPERATORS: Final[tuple[str, ...]] = ("&", "|", "<", ">", "^", "!", '"', "\x1a")  # fmt: skip

_PATH_REPLACEMENT_NAMES: Final[MappingProxyType[str, str]] = MappingProxyType({
    "__VIRTUAL_ENV__": "the destination directory",
    "__TCL_LIBRARY__": "the interpreter's Tcl library path",
    "__TK_LIBRARY__": "the interpreter's Tk library path",
})


class BatchActivator(ViaTemplateActivator):  # fmt: skip
    """Generate the ``activate.bat``, ``deactivate.bat`` and ``pydoc.bat`` scripts for ``cmd.exe``."""

    @classmethod
    def supports(cls, interpreter: PythonInfo) -> bool:
        """Accept interpreters on Windows.

        :param interpreter: the host interpreter to check

        :returns: ``True`` when the interpreter runs on Windows

        """
        return interpreter.os == "nt"

    def generate(self, creator: Creator) -> list[Path]:
        """Generate the scripts, or remove them when a path holds a character that batch cannot represent.

        :param creator: the creator of the environment

        :returns: the paths of the generated scripts, empty when they were removed

        """
        return [] if self.remove_unsafe(creator) else super().generate(creator)

    def remove_unsafe(self, creator: Creator, *, selected: bool = True) -> bool:
        """Remove the scripts when a path holds a character that batch cannot represent.

        :param creator: the creator of the environment
        :param selected: ``True`` to log the problems as warnings, ``False`` to log them at debug level

        :returns: ``True`` when the scripts were removed

        """
        values = super().replacements(creator, creator.bin_dir)
        if problems := [reason for key in _PATH_REPLACEMENT_NAMES if (reason := _unsafe_path_reason(key, values[key]))]:
            for problem in problems:
                LOGGER.log(
                    logging.WARNING if selected else logging.DEBUG, "skipping batch activation scripts: %s", problem
                )
            for template in self.templates():
                (creator.bin_dir / self.as_name(template)).unlink(missing_ok=True)
            return True
        return False

    def templates(self) -> Iterator[str]:
        """The template file names to instantiate.

        :yields: the template file names

        """
        yield "activate.bat"
        yield "deactivate.bat"
        yield "pydoc.bat"

    def instantiate_template(self, replacements: dict[str, str], template: str, creator: Creator) -> str:
        """Fill the placeholders and end every line with the platform line separator, which batch requires.

        :param replacements: the raw placeholder values
        :param template: the name of the template file
        :param creator: the creator of the environment

        :returns: the template text with every placeholder replaced

        """
        # ensure the text has all newlines as \r\n - required by batch
        base = super().instantiate_template(replacements, template, creator)
        return base.replace(os.linesep, "\n").replace("\n", os.linesep)

    def substitutions(self, replacements: dict[str, str], creator: Creator) -> dict[str, str]:
        """Add the quoted environment path, with its ``%`` escaped for batch, to the placeholder values.

        :param replacements: the raw placeholder values
        :param creator: the creator of the environment

        :returns: the placeholder names mapped to their substituted text

        """
        return {
            **super().substitutions(replacements, creator),
            "__BATCH_ASSIGN__": "\n".join(read_binary(__name__, "_assign.bat").decode("ascii").splitlines()),
            "__VIRTUAL_ENV_CALL__": self.quote(replacements["__VIRTUAL_ENV__"]).replace("%", "%%"),
        }

    @staticmethod
    def quote(string: str) -> str:
        """Make a value safe to sit inside ``@set "VAR=value"``.

        Batch has no escape for a double quote in this context either: it always closes the quoted string, and whatever
        follows on the line runs as live cmd.exe syntax. A raw line boundary is worse - batch is line-oriented
        regardless of quote state, so it starts a brand-new statement instead of staying inside the value. None of these
        can be represented literally here, so replace them with a space. ``%`` still triggers variable expansion inside
        the quotes, but doubling it to ``%%`` is a real, in-file escape that keeps the literal character.

        :param string: the value to make safe for the ``@set`` line

        :returns: the value with ``%`` doubled and operators and line boundaries replaced by spaces

        """
        string = string.replace("%", "%%")
        for operator in _CMD_OPERATORS:
            string = string.replace(operator, " ")
        return collapse_line_boundaries(string)


def _unsafe_path_reason(key: str, value: str) -> str | None:  # fmt: skip
    found = sorted({char for char in value if char in _CMD_OPERATORS or collapse_line_boundaries(char) != char})
    if not found:
        return None
    return (
        f"{_PATH_REPLACEMENT_NAMES[key]} ({value!r}) contains {''.join(found)!r}, which the batch activator "
        "cannot preserve in generated scripts"
    )


__all__ = [
    "BatchActivator",
]
