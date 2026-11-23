"""Shared text-safety helpers for values written into line-based formats."""

from __future__ import annotations

__lazy_modules__ = ["typing"]

from typing import Final

# A line-based format with no escape syntax reads any character str.splitlines() treats as a
# boundary back as an extra line - or, for a script, runs it as one. This is the exact boundary
# set splitlines() recognizes, per the Python string documentation.
_LINE_BOUNDARIES: Final[tuple[str, ...]] = (
    "\n",
    "\r",
    "\v",
    "\f",
    "\x1c",
    "\x1d",
    "\x1e",
    "\x85",
    chr(0x2028),  # line separator
    chr(0x2029),  # paragraph separator
)


def collapse_line_boundaries(text: str) -> str:
    """Replace every line-boundary character with a space so text can never become extra lines.

    :param text: the text to collapse

    :returns: the text with every line-boundary character replaced by a space

    """
    for boundary in _LINE_BOUNDARIES:
        text = text.replace(boundary, " ")
    return text


__all__ = [
    "collapse_line_boundaries",
]
