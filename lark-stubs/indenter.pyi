# -*- coding: utf-8 -*-

from typing import Tuple, List, Iterator, Optional
from abc import ABC, abstractmethod
from .lexer import Token


class Indenter(ABC):
    paren_level: Optional[int]
    indent_level: Optional[List[int]]

    def __init__(self):
        ...

    def handle_NL(self, token: Token) -> Iterator[Token]:
        ...

    def process(self, stream: Iterator[Token]) -> Iterator[Token]:
        ...

    @property
    def always_accept(self) -> Tuple[str]:
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
