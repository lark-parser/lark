"""
Tracing utils
"""

from __future__ import annotations

from collections.abc import Callable
from collections.abc import Sequence
import enum
import os
from typing import Any


_Writer = Callable[[str], object]
_Processor = Callable[[tuple[str, ...], tuple[Any, ...]], object]


def _describe_failure(exc: Exception, obj: object, func: str) -> str:
    try:
        exc_info = repr(exc)
    except Exception:
        exc_info = f"unpresentable {type(exc).__name__}"
    name = type(obj).__name__
    return f"<[{exc_info} raised in {func}()] {name} object at 0x{id(obj):x}>"


def _escape_surrogates(text: str) -> str:
    """Escape lone surrogates so the result survives any text writer.

    A lone surrogate reaching the writer raises :exc:`UnicodeEncodeError`
    inside the trace call for any utf-8 target, such as the file behind
    pytest's ``--debug``.
    """
    if text.isascii():
        return text
    return text.encode("utf-8", "backslashreplace").decode("utf-8")


def _safe_str(obj: object) -> str:
    """``str(obj)`` for tracing, with a failing ``__str__`` rendered, not raised.

    The result has lone surrogates escaped, so any text writer accepts it.
    """
    try:
        text = str(obj)
    except Exception as exc:
        text = _describe_failure(exc, obj, "str")
    return _escape_surrogates(text)


def _is_plain_token(text: str) -> bool:
    """Whether ``text`` can be shown bare, without quotes around it."""
    return bool(text) and text.isprintable() and " " not in text


def _format_block(indent: str, lines: list[str]) -> list[str]:
    """Indent a multi line value under its key, so it reads as one value."""
    return [f"{indent}      {line}\n" for line in lines]


def _render_value(obj: object) -> str:
    """Render a traced value, adding detail only where ``str`` is ambiguous."""
    # Before the str check: a StrEnum member is a str whose str() drops the name.
    if isinstance(obj, (enum.Enum, os.PathLike)):
        return _safe_repr(obj)
    if isinstance(obj, str):
        if len(obj.splitlines()) > 1:
            return _safe_str(obj)
        if _is_plain_token(obj):
            return _safe_str(obj)
        return _safe_repr(obj)
    return _safe_str(obj)


def _safe_repr(obj: object) -> str:
    """``repr(obj)`` for tracing, with a failing ``__repr__`` rendered, not raised.

    The result has lone surrogates escaped, so any text writer accepts it.
    """
    try:
        text = repr(obj)
    except Exception as exc:
        text = _describe_failure(exc, obj, "repr")
    return _escape_surrogates(text)


class TagTracer:
    def __init__(self) -> None:
        self._tags2proc: dict[tuple[str, ...], _Processor] = {}
        self._writer: _Writer | None = None
        self.indent = 0

    def get(self, name: str) -> TagTracerSub:
        return TagTracerSub(self, (name,))

    def _format_message(self, tags: Sequence[str], args: Sequence[object]) -> str:
        if isinstance(args[-1], dict):
            extra = args[-1]
            args = args[:-1]
        else:
            extra = {}

        content = " ".join(map(_safe_str, args))
        indent = "  " * self.indent

        lines = [f"{indent}{content} [{':'.join(tags)}]\n"]

        for name, value in extra.items():
            rendered = _render_value(value)
            # A bare \r is a line break too: inline, the terminal would
            # return to column 0 and overwrite the key.
            body = rendered.splitlines()
            if body in ([], [rendered]):
                lines.append(f"{indent}    {name}: {rendered}\n")
            else:
                lines.append(f"{indent}    {name}:\n")
                lines.extend(_format_block(indent, body))

        return "".join(lines)

    def _processmessage(self, tags: tuple[str, ...], args: tuple[object, ...]) -> None:
        if self._writer is not None and args:
            self._writer(self._format_message(tags, args))
        if processor := self._tags2proc.get(tags):
            processor(tags, args)

    def setwriter(self, writer: _Writer | None) -> None:
        self._writer = writer

    def setprocessor(self, tags: str | tuple[str, ...], processor: _Processor) -> None:
        if isinstance(tags, str):
            tags = tuple(tags.split(":"))
        else:
            assert isinstance(tags, tuple)
        self._tags2proc[tags] = processor


class TagTracerSub:
    def __init__(self, root: TagTracer, tags: tuple[str, ...]) -> None:
        self.root = root
        self.tags = tags

    def __call__(self, *args: object) -> None:
        self.root._processmessage(self.tags, args)

    def get(self, name: str) -> TagTracerSub:
        return self.__class__(self.root, self.tags + (name,))
