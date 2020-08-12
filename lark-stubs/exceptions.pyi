# -*- coding: utf-8 -*-

from typing import Dict, Iterable, Callable, Union, TypeVar, Tuple, Any, List, Set
from .tree import Tree
from .lexer import Token


class LarkError(Exception):
    pass


class GrammarError(LarkError):
    pass


class ParseError(LarkError):
    pass


class LexError(LarkError):
    pass


T = TypeVar('T')


class UnexpectedInput(LarkError):
    line: int
    column: int
    pos_in_stream: int
    state: Any

    def get_context(self, text: str, span: int = ...):
        ...

    def match_examples(
            self,
            parse_fn: Callable[[str], Tree],
            examples: Union[Dict[T, Iterable[str]], Iterable[Tuple[T, Iterable[str]]]],
            token_type_match_fallback: bool = False,
            print_debug_info: bool = True
    ) -> T:
        ...


class UnexpectedToken(ParseError, UnexpectedInput):
    expected: List[str]
    considered_rules: Set[str]
    puppet: Any
    accepts: List[str]

class UnexpectedCharacters(LexError, UnexpectedInput):
    allowed: Set[str]
    considered_tokens: Set[Any]


class VisitError(LarkError):
    obj: Union[Tree, Token]
    orig_exc: Exception
