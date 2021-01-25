# -*- coding: utf-8 -*-

from typing import Dict, Iterable, Callable, Union, TypeVar, Tuple, Any, List, Set
from .tree import Tree
from .lexer import Token
from .parsers.lalr_puppet import ParserPuppet

class LarkError(Exception):
    pass


class ConfigurationError(LarkError, ValueError):
    pass


class GrammarError(LarkError):
    pass


class ParseError(LarkError):
    pass


class LexError(LarkError):
    pass


T = TypeVar('T')

class UnexpectedEOF(ParseError):
    expected: List[Token]

class UnexpectedInput(LarkError):
    line: int
    column: int
    pos_in_stream: int
    state: Any

    def get_context(self, text: str, span: int = ...) -> str:
        ...

    def match_examples(
            self,
            parse_fn: Callable[[str], Tree],
            examples: Union[Dict[T, Iterable[str]], Iterable[Tuple[T, Iterable[str]]]],
            token_type_match_fallback: bool = False,
            use_accepts: bool = False,
    ) -> T:
        ...


class UnexpectedToken(ParseError, UnexpectedInput):
    expected: Set[str]
    considered_rules: Set[str]
    puppet: ParserPuppet
    accepts: Set[str]

class UnexpectedCharacters(LexError, UnexpectedInput):
    allowed: Set[str]
    considered_tokens: Set[Any]


class VisitError(LarkError):
    obj: Union[Tree, Token]
    orig_exc: Exception
