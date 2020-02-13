# -*- coding: utf-8 -*-

from typing import List, Dict, IO, Callable, Union, Optional, Literal
from .visitors import Transformer
from .lexer import Lexer, Token
from .tree import Tree

_Start = Union[None, str, List[str]]


class Lark:

    def __init__(
        self,
        grammar: Union[str, IO[str]],
        *,
        start: _Start = ...,
        parser: Literal["earley", "lalr", "cyk"] = ...,
        lexer: Optional[Lexer] = ...,
        transformer: Optional[Transformer] = ...,
        postlex: Optional[Literal["standard", "contextual"]] = ...,
        ambiguity: Literal["explicit", "resolve"] = ...,
        debug: bool = False,
        keep_all_tokens: bool = False,
        propagate_positions: bool = False,
        maybe_placeholders: bool = False,
        lexer_callbacks: Dict[str, Callable[[Token], Token]]
    ):
        ...

    def parse(self, text: str, start: _Start = None) -> Tree:
        ...
