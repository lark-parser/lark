# -*- coding: utf-8 -*-

from typing import (
    TypeVar, Type, List, Dict, IO, Iterator, Callable, Union, Optional,
    Literal, Protocol,
)
from .visitors import Transformer
from .lexer import Token, Lexer, TerminalDef
from .tree import Tree

_T = TypeVar('_T')

class PostLex(Protocol):

    def process(self, stream: Iterator[Token]) -> Iterator[Token]:
        ...


class LarkOptions:
    start: List[str]
    parser: str
    lexer: str
    transformer: Optional[Transformer]
    postlex: Optional[PostLex]
    ambiguity: str
    regex: bool
    debug: bool
    keep_all_tokens: bool
    propagate_positions: bool
    maybe_placeholders: bool
    lexer_callbacks: Dict[str, Callable[[Token], Token]]
    cache: Union[bool, str]
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
        start: Union[None, str, List[str]] = "start",
        parser: Literal["earley", "lalr", "cyk"] = "auto",
        lexer: Union[Literal["auto", "standard", "contextual", "dynamic", "dynamic_complete"], Lexer] = "auto",
        transformer: Optional[Transformer] = None,
        postlex: Optional[PostLex] = None,
        ambiguity: Literal["explicit", "resolve"] = "resolve",
        regex: bool = False,
        debug: bool = False,
        keep_all_tokens: bool = False,
        propagate_positions: bool = False,
        maybe_placeholders: bool = False,
        lexer_callbacks: Optional[Dict[str, Callable[[Token], Token]]] = None,
        g_regex_flags: int = ...
    ):
        ...

    def parse(self, text: str, start: Optional[str] = None) -> Tree:
        ...

    @classmethod
    def open(cls: Type[_T], grammar_filename: str, rel_to: Optional[str] = None, **options) -> _T:
        ...

    def lex(self, text: str) -> Iterator[Token]:
        ...

    def get_terminal(self, name: str) -> TerminalDef:
        ...
