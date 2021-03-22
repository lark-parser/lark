# -*- coding: utf-8 -*-

from typing import Tuple, List, Iterator, Optional
from abc import ABC, abstractmethod
from .lexer import Token
from .lark import PostLex


class Indenter(PostLex, ABC):
    paren_level: Optional[int]
    indent_level: Optional[List[int]]

    def __init__(self) -> None:
        ...

    def handle_NL(self, token: Token) -> Iterator[Token]:
        ...

    @property
    @abstractmethod
    def NL_type(self) -> str:
        ...

    @property
    @abstractmethod
    def OPEN_PAREN_types(self) -> List[str]:
        ...

    @property
    @abstractmethod
    def CLOSE_PAREN_types(self) -> List[str]:
        ...

    @property
    @abstractmethod
    def INDENT_type(self) -> str:
        ...

    @property
    @abstractmethod
    def DEDENT_type(self) -> str:
        ...

    @property
    @abstractmethod
    def tab_len(self) -> int:
        ...
