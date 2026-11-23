from __future__ import annotations

__lazy_modules__ = [
    "shlex",
    "virtualenv.util.text",
]

import logging  # isort: skip # fmt: skip
import re  # isort: skip # fmt: skip
import shlex  # isort: skip # fmt: skip
from typing import TYPE_CHECKING, Final  # isort: skip # fmt: skip

from virtualenv.activation.via_template import ViaTemplateActivator  # isort: skip # fmt: skip
from virtualenv.util.text import collapse_line_boundaries  # isort: skip # fmt: skip

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from python_discovery import PythonInfo

    from virtualenv.create.creator import Creator

_LOGGER: Final[logging.Logger] = logging.getLogger(__name__)  # fmt: skip
_NON_ASCII: Final[re.Pattern[str]] = re.compile(r"[^\x00-\x7f]")
_STATEFUL_UTF8: Final[re.Pattern[bytes]] = re.compile(rb"\x88[\xa3\xa5\xa7]")


class CShellActivator(ViaTemplateActivator):  # fmt: skip
    """Generate the ``activate.csh`` and ``deactivate.csh`` scripts for csh and tcsh."""

    @classmethod
    def supports(cls, interpreter: PythonInfo) -> bool:
        """Accept interpreters that are not on Windows.

        :param interpreter: the host interpreter to check

        :returns: ``True`` when the interpreter does not run on Windows

        """
        return interpreter.os != "nt"

    def generate(self, creator: Creator) -> list[Path]:
        """Generate the scripts, or remove them when a path holds a newline.

        :param creator: the creator of the environment

        :returns: the paths of the generated scripts, empty when they were removed

        """
        values: Final[dict[str, str]] = super().replacements(creator, creator.bin_dir)
        if any("\n" in values[key] for key in ("__VIRTUAL_ENV__", "__TCL_LIBRARY__", "__TK_LIBRARY__")):
            _LOGGER.warning("skipping csh activation scripts: a filesystem path contains a newline")
            for template in self.templates():
                (creator.bin_dir / self.as_name(template)).unlink(missing_ok=True)
            return []
        return super().generate(creator)

    def templates(self) -> Iterator[str]:
        """The template file names to instantiate.

        :yields: the template file names

        """
        yield "activate.csh"
        yield "deactivate.csh"

    @staticmethod
    def quote(string: str) -> str:
        """Quote the value for csh, keeping history expansion, percent signs and backslashes inert.

        :param string: the value to quote

        :returns: the quoted value

        """
        # csh expands history inside single quotes and parses unquoted percent signs as expression operators.
        # Backslashes outside quotes retain their meaning with tcsh's backslash_quote option.
        quoted: Final[str] = shlex.quote(string)
        return (f"'{quoted}'" if quoted == string else quoted).replace("\\", "'\\\\'").replace("!", "'\\!'")

    def substitutions(self, replacements: dict[str, str], creator: Creator) -> dict[str, str]:
        """Add the escaped display prompt for tcsh and plain csh to the placeholder values.

        :param replacements: the raw placeholder values
        :param creator: the creator of the environment

        :returns: the placeholder names mapped to their substituted text

        """
        # Normalize display text without changing the filesystem paths used by activation.
        values: Final[dict[str, str]] = {
            **replacements,
            "__VIRTUAL_PROMPT__": collapse_line_boundaries(replacements["__VIRTUAL_PROMPT__"]),
        }
        display: Final[str] = collapse_line_boundaries(
            creator.env_name if self.flag_prompt is None else self.flag_prompt
        )
        literals = super().substitutions(values, creator)
        # Stateful legacy encoders can consume the shell quote after these UTF-8 suffixes.
        needs_command = _STATEFUL_UTF8.search(display.encode("utf-8", "surrogateescape")) is not None
        return {
            **{key: _NON_ASCII.sub(self._bytes_apart, literal) for key, literal in literals.items()},
            "__VIRTUAL_PROMPT_DISPLAY_TCSH__": "''" if needs_command else _prompt_literal(display, tcsh=True),
            "__VIRTUAL_PROMPT_DISPLAY_PLAIN__": "''" if needs_command else _prompt_literal(display, tcsh=False),
            "__VIRTUAL_PROMPT_PREFIX_TCSH__": _prompt_command(display, tcsh=True)
            if needs_command
            else """'('"$_virtualenv_prompt_tcsh:q"') '""",
            "__VIRTUAL_PROMPT_PREFIX_PLAIN__": _prompt_command(display, tcsh=False)
            if needs_command
            else """'('"$_virtualenv_prompt_plain:q"') '""",
        }

    @staticmethod
    def _bytes_apart(match: re.Match[str]) -> str:
        # tcsh retains undecodable bytes; decoded characters can become punctuation after a locale change.
        return "".join(f"{chr(0xDC00 + byte)}''" for byte in match.group().encode("utf-8", "surrogateescape"))


def _prompt_literal(value: str, *, tcsh: bool) -> str:  # fmt: skip
    # Prompt drawing interprets history escapes and tcsh percent codes a second time.
    parts = ["'"]
    for char in value:
        if char == "'":
            parts.append("'\"'\"'")
        elif char == "!":
            parts.append("'\\\\'\\!")
        elif char == "%" and tcsh:
            parts.append("%%")
        elif char == "^" and tcsh:
            parts.append("'\\\\^'")
        elif char == "\\":
            parts.append("'\\\\\\\\'" if tcsh else "'\\\\'")
        else:
            parts.append(char)
    parts.append("'")
    return "".join(parts)


def _prompt_command(value: str, *, tcsh: bool) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "%%").replace("^", "\\^") if tcsh else value
    escaped = escaped.replace("!", "\\!")
    return (
        "\"`$_virtualenv_printf '%b' '"
        + "".join(f"\\0{byte:03o}" for byte in f"({escaped})".encode("utf-8", "surrogateescape"))
        + "'`\"' '"
    )


__all__ = [
    "CShellActivator",
]
