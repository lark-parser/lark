# -*- coding: utf-8 -*-

from typing import Tuple, Iterator, Sized
from abc import abstractmethod, ABC


class Pattern(ABC):

    @abstractmethod
    def to_regexp(self) -> str:
        ...


class PatternStr(Pattern):

    def to_regexp(self) -> str:
        ...


class PatternRE(Pattern):

    def to_regexp(self) -> str:
        ...


class TerminalDef:
    name: str
    pattern: Pattern
    priority: int


class Token(str):
    type: str
    pos_in_stream: int
    line: int
    column: int
    end_line: int
    end_column: int
    end_pos: int


class Lexer(ABC):

    @abstractmethod
    def lex(self, stream: Sized) -> Iterator[Token]:
        ...


class TraditionalLexer(Lexer):

    def build(self) -> None:
        ...

    def match(self, stream: str, pos: int) -> Tuple[str, str]:
        ...

    def lex(self, stream: Sized) -> Iterator[Token]:
        ...


class ContextualLexer(Lexer):

    def lex(self, stream: Sized) -> Iterator[Token]:
        ...
