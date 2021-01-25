# -*- coding: utf-8 -*-
from types import ModuleType
from typing import (
    TypeVar, Type, Tuple, List, Dict, Iterator, Collection, Callable, Optional, FrozenSet, Any,
    Pattern as REPattern,
)
from abc import abstractmethod, ABC

_T = TypeVar('_T')


class Pattern(ABC):
    value: str
    flags: Collection[str]
    raw: str
    type: str

    def __init__(self, value: str, flags: Collection[str] = (), raw: str = None) -> None:
        ...

    @abstractmethod
    def to_regexp(self) -> str:
        ...

    @property
    @abstractmethod
    def min_width(self) -> int:
        ...

    @property
    @abstractmethod
    def max_width(self) -> int:
        ...


class PatternStr(Pattern):
    type: str = ...

    def to_regexp(self) -> str:
        ...

    @property
    def min_width(self) -> int:
        ...

    @property
    def max_width(self) -> int:
        ...


class PatternRE(Pattern):
    type: str = ...

    def to_regexp(self) -> str:
        ...

    @property
    def min_width(self) -> int:
        ...

    @property
    def max_width(self) -> int:
        ...


class TerminalDef:
    name: str
    pattern: Pattern
    priority: int

    def __init__(self, name: str, pattern: Pattern, priority: int = ...) -> None:
        ...

    def user_repr(self) -> str: ...


class Token(str):
    type: str
    pos_in_stream: int
    value: Any
    line: int
    column: int
    end_line: int
    end_column: int
    end_pos: int

    def __init__(self, type_: str, value: Any, pos_in_stream: int = None, line: int = None, column: int = None, end_line: int = None, end_column: int = None, end_pos: int = None) -> None:
        ...

    def update(self, type_: Optional[str] = None, value: Optional[Any] = None) -> Token:
        ...

    @classmethod
    def new_borrow_pos(cls: Type[_T], type_: str, value: Any, borrow_t: Token) -> _T:
        ...


_Callback = Callable[[Token], Token]


class Lexer(ABC):
    lex: Callable[..., Iterator[Token]]


class LexerConf:
     tokens: Collection[TerminalDef]
     re_module: ModuleType
     ignore: Collection[str] = ()
     postlex: Any =None
     callbacks: Optional[Dict[str, _Callback]] = None
     g_regex_flags: int = 0
     skip_validation: bool = False
     use_bytes: bool = False



class TraditionalLexer(Lexer):
    terminals: Collection[TerminalDef]
    ignore_types: FrozenSet[str]
    newline_types: FrozenSet[str]
    user_callbacks: Dict[str, _Callback]
    callback: Dict[str, _Callback]
    mres: List[Tuple[REPattern, Dict[int, str]]]
    re: ModuleType

    def __init__(
        self,
        conf: LexerConf
    ) -> None:
        ...

    def build(self) -> None:
        ...

    def match(self, stream: str, pos: int) -> Optional[Tuple[str, str]]:
        ...

    def lex(self, stream: str) -> Iterator[Token]:
        ...

    def next_token(self, lex_state: Any, parser_state: Any = None) -> Token:
        ...

class ContextualLexer(Lexer):
    lexers: Dict[str, TraditionalLexer]
    root_lexer: TraditionalLexer

    def __init__(
        self,
        terminals: Collection[TerminalDef],
        states: Dict[str, Collection[str]],
        re_: ModuleType,
        ignore: Collection[str] = ...,
        always_accept: Collection[str] = ...,
        user_callbacks: Dict[str, _Callback] = ...,
        g_regex_flags: int = ...
    ) -> None:
        ...

    def lex(self, stream: str, get_parser_state: Callable[[], str]) -> Iterator[Token]:
        ...
