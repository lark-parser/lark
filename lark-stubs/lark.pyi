# -*- coding: utf-8 -*-

from typing import (
    Type, List, Dict, IO, Iterator, Callable, Union, Optional,
    Literal, Protocol, Tuple, Iterable,
)

from .visitors import Transformer
from .lexer import Token, Lexer, TerminalDef
from .load_grammar import Grammar, PackageResource

class PostLex(Protocol):

    def process(self, stream: Iterator[Token]) -> Iterator[Token]:
        ...

    always_accept: Iterable[str]

class LarkOptions:
    ...

class Lark:
    source_path: str
    source_grammar: str
    grammar: Grammar
    options: LarkOptions
    lexer: Lexer
    terminals: List[TerminalDef]

    def __init__(
        self,
        grammar: Union[Grammar, str, IO[str]],
        *,
        start: Union[None, str, List[str]] = "start",
        parser: Literal["earley", "lalr", "cyk", "auto"] = "auto",
        lexer: Union[Literal["auto", "standard", "contextual", "dynamic", "dynamic_complete"], Type[Lexer]] = "auto",
        transformer: Optional[Transformer] = None,
        postlex: Optional[PostLex] = None,
        ambiguity: Literal["explicit", "resolve"] = "resolve",
        regex: bool = False,
        debug: bool = False,
        keep_all_tokens: bool = False,
        propagate_positions: Union[bool, str] = False,
        maybe_placeholders: bool = False,
        lexer_callbacks: Optional[Dict[str, Callable[[Token], Token]]] = None,
        cache: Union[bool, str] = False,
        g_regex_flags: int = ...,
        use_bytes: bool = False,
        import_paths: List[Union[str, Callable[[Union[None, str, PackageResource], str], Tuple[str, str]]]] = ...,
        source_path: Optional[str]=None,
    ):
        ...

