# -*- coding: utf-8 -*-

from typing import (
    TypeVar, Type, List, Dict, IO, Iterator, Callable, Union, Optional,
    Literal, Protocol, Tuple, Iterable,
)

from .parsers.lalr_interactive_parser import InteractiveParser
from .visitors import Transformer
from .lexer import Token, Lexer, TerminalDef
from .tree import Tree
from .exceptions import UnexpectedInput
from .load_grammar import Grammar

_T = TypeVar('_T')


class PostLex(Protocol):

    def process(self, stream: Iterator[Token]) -> Iterator[Token]:
        ...

    always_accept: Iterable[str]


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
    use_bytes: bool
    import_paths: List[Union[str, Callable[[Union[None, str, PackageResource], str], Tuple[str, str]]]]
    source_path: Optional[str]


class PackageResource(object):
    pkg_name: str
    path: str

    def __init__(self, pkg_name: str, path: str): ...


class FromPackageLoader:
    def __init__(self, pkg_name: str, search_paths: Tuple[str, ...] = ...): ...

    def __call__(self, base_path: Union[None, str, PackageResource], grammar_path: str) -> Tuple[PackageResource, str]: ...


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
        propagate_positions: bool = False,
        maybe_placeholders: bool = False,
        lexer_callbacks: Optional[Dict[str, Callable[[Token], Token]]] = None,
        cache: Union[bool, str] = False,
        g_regex_flags: int = ...,
        use_bytes: bool = False,
        import_paths: List[Union[str, Callable[[Union[None, str, PackageResource], str], Tuple[str, str]]]] = ...,
        source_path: Optional[str]=None,
    ):
        ...

    def parse(self, text: str, start: Optional[str] = None, on_error: Callable[[UnexpectedInput], bool] = None) -> Tree:
        ...

    def parse_interactive(self, text: str = None, start: Optional[str] = None) -> InteractiveParser:
        ...

    @classmethod
    def open(cls: Type[_T], grammar_filename: str, rel_to: Optional[str] = None, **options) -> _T:
        ...

    @classmethod
    def open_from_package(cls: Type[_T], package: str, grammar_path: str, search_paths: Tuple[str, ...] = ..., **options) -> _T:
        ...

    def lex(self, text: str, dont_ignore: bool = False) -> Iterator[Token]:
        ...

    def get_terminal(self, name: str) -> TerminalDef:
        ...
