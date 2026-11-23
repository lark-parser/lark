from __future__ import annotations

from typing import TYPE_CHECKING  # isort: skip # fmt: skip

from virtualenv.activation.via_template import ViaTemplateActivator  # isort: skip # fmt: skip

if TYPE_CHECKING:
    from collections.abc import Iterator


class PowerShellActivator(ViaTemplateActivator):  # fmt: skip
    """Generate the ``activate.ps1`` script for PowerShell."""

    def templates(self) -> Iterator[str]:
        """The template file names to instantiate.

        :yields: the template file names

        """
        yield "activate.ps1"

    @staticmethod
    def quote(string: str) -> str:
        """Quote by PowerShell's rules [1], unless the string is passed straight to a Windows native command [2].

        [1]: https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_quoting_rules
        [2]:
        https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_parsing#passing-arguments-that-contain-quote-characters

        :param string: the value to quote

        :returns: the value wrapped in single quotes, with every single-quote character doubled

        """
        # PowerShell treats the ASCII apostrophe and the curly single quotes U+2018-U+201B as
        # interchangeable single-quote delimiters, so each must be doubled to stay inert inside the literal.
        for point in (0x27, 0x2018, 0x2019, 0x201A, 0x201B):
            delimiter = chr(point)
            string = string.replace(delimiter, delimiter * 2)
        return f"'{string}'"


__all__ = [
    "PowerShellActivator",
]
