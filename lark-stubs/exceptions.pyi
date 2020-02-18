# -*- coding: utf-8 -*-

from typing import Dict, Iterable, Callable
from .tree import Tree


class LarkError(Exception):
    pass


class GrammarError(LarkError):
    pass


class ParseError(LarkError):
    pass


class LexError(LarkError):
    pass


class UnexpectedInput(LarkError):
    pos_in_stream: int

    def get_context(self, text: str, span: int = ...):
        ...

    def match_examples(
        self,
        parse_fn: Callable[[str], Tree],
        examples: Dict[str, Iterable[str]]
    ):
        ...


class UnexpectedToken(ParseError, UnexpectedInput):
    pass


class UnexpectedCharacters(LexError, UnexpectedInput):
    line: int
    column: int


class VisitError(LarkError):
    pass
