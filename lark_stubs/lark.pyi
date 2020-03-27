# -*- coding: utf-8 -*-

from typing import (
    TypeVar, Type, List, Dict, IO, Iterator, Callable, Union, Optional,
    Literal, Protocol,
)
from .visitors import Transformer
from .lexer import Token, Lexer, TerminalDef
from .tree import Tree

_T = TypeVar('_T')
_Start = Union[None, str, List[str]]
_Parser = Literal["earley", "lalr", "cyk"]
_Lexer = Union[Literal["auto", "standard", "contextual", "dynamic", "dynamic_complete"], Lexer]
_Ambiguity = Literal["explicit", "resolve"]


class PostLex(Protocol):

    def process(self, stream: Iterator[Token]) -> Iterator[Token]:
        ...


class LarkOptions:
    start: _Start
    parser: _Parser
    lexer: _Lexer
    transformer: Optional[Transformer]
    postlex: Optional[PostLex]
    ambiguity: _Ambiguity
    debug: bool
    keep_all_tokens: bool
    propagate_positions: bool
    maybe_placeholders: bool
    lexer_callbacks: Dict[str, Callable[[Token], Token]]
    cache_grammar: bool
    g_regex_flags: int


class Lark:
    source: str
    options: LarkOptions
    lexer: Lexer
    terminals: List[TerminalDef]

    def __init__(
        self,
        grammar: Union[str, IO[str]],
        *,
        start: _Start = ...,
        parser: _Parser = ...,
        lexer: _Lexer = ...,
        transformer: Optional[Transformer] = None,
        postlex: Optional[PostLex] = None,
        ambiguity: _Ambiguity = ...,
        debug: bool = False,
        keep_all_tokens: bool = False,
        propagate_positions: bool = False,
        maybe_placeholders: bool = False,
        lexer_callbacks: Optional[Dict[str, Callable[[Token], Token]]] = None,
        g_regex_flags: int = ...
    ):
        ...

    def parse(self, text: str, start: _Start = None) -> Tree:
        ...

    @classmethod
    def open(cls: Type[_T], grammar_filename: str, rel_to: Optional[str] = None, **options) -> _T:
        ...

    def lex(self, text: str) -> Iterator[Token]:
        ...

    def get_terminal(self, name: str) -> TerminalDef:
        ...
