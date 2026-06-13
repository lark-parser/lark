from abc import ABC, abstractmethod
import sys, os
import types
import re
from typing import (
    TypeVar, Type, List, Dict, Iterator, Callable, Union, Optional, Sequence,
    Tuple, Iterable, IO, Any, TYPE_CHECKING, Collection, Generic, overload,
)
if TYPE_CHECKING:
    from .parsers.lalr_interactive_parser import InteractiveParser
    from .tree import ParseTree
    from .visitors import Transformer
    from typing import Literal
    from .parser_frontends import ParsingFrontend

from .exceptions import ConfigurationError, assert_config, UnexpectedInput
from .utils import Serialize, FS, logger, TextOrSlice, LarkInput
from .serialize import SerializeMemoizer
from .load_grammar import load_grammar, FromPackageLoader, Grammar, verify_used_files, PackageResource, sha256_digest

from .tree import Tree
from .common import LexerConf, ParserConf, _ParserArgType, _LexerArgType

from .lexer import Lexer, BasicLexer, TerminalDef, LexerThread, Token
from .visitors import _Return_T
from .parse_tree_builder import ParseTreeBuilder
from .parser_frontends import _validate_frontend_args, _get_lexer_callbacks, _deserialize_parsing_frontend, _construct_parsing_frontend
from .grammar import Rule

# Import from new modules
from .options import LarkOptions, _LOAD_ALLOWED_OPTIONS, _VALID_PRIORITY_OPTIONS, _VALID_AMBIGUITY_OPTIONS
from .persistence import (
    lark_save, lark_load, lark_load_into, lark_load_from_dict,
    resolve_cache_fn, load_from_cache, save_to_cache, lark_deserialize_lexer_conf,
)


try:
    import regex
    _has_regex = True
except ImportError:
    _has_regex = False


###{standalone


class PostLex(ABC):
    @abstractmethod
    def process(self, stream: Iterator[Token]) -> Iterator[Token]:
        return stream

    always_accept: Iterable[str] = ()


# Options that can be passed to the Lark parser, even when it was loaded from cache/standalone.
# These options are only used outside of `load_grammar`.
_LOAD_ALLOWED_OPTIONS = _LOAD_ALLOWED_OPTIONS

_VALID_PRIORITY_OPTIONS = _VALID_PRIORITY_OPTIONS
_VALID_AMBIGUITY_OPTIONS = _VALID_AMBIGUITY_OPTIONS


_T = TypeVar('_T', bound="Lark")
_InitReturn_T = TypeVar('_InitReturn_T') # __init__ self annotations must use a new type-var

class Lark(Serialize, Generic[_Return_T]):
    """Main interface for the library.

    It's mostly a thin wrapper for the many different parsers, and for the tree constructor.

    Parameters:
        grammar: a string or file-object containing the grammar spec (using Lark's ebnf syntax)
        options: a dictionary controlling various aspects of Lark.

    Example:
        >>> Lark(r'''start: "foo" ''')
        Lark(...)
    """

    source_path: str
    source_grammar: str
    grammar: 'Grammar'
    options: LarkOptions
    lexer: Lexer
    parser: 'ParsingFrontend'
    terminals: Collection[TerminalDef]

    __serialize_fields__ = ['parser', 'rules', 'options']

    @overload
    def __init__(
        self: 'Lark[_InitReturn_T]',
        grammar: 'Union[Grammar, str, IO[str]]',
        *,
        transformer: 'Transformer[Token, _InitReturn_T]',
        **options: Any,
    ) -> None: ...

    @overload
    def __init__(
        self: 'Lark[ParseTree]',
        grammar: 'Union[Grammar, str, IO[str]]',
        **options: Any,
    ) -> None: ...

    def __init__(self, grammar: 'Union[Grammar, str, IO[str]]', **options) -> None:
        self.options = LarkOptions(options)
        re_module: types.ModuleType

        # Update which fields are serialized
        if self.options.cache_grammar:
            self.__serialize_fields__ = self.__serialize_fields__ + ['grammar']

        # Set regex or re module
        use_regex = self.options.regex
        if use_regex:
            if _has_regex:
                re_module = regex
            else:
                raise ImportError('`regex` module must be installed if calling `Lark(regex=True)`.')
        else:
            re_module = re

        # Some, but not all file-like objects have a 'name' attribute
        if self.options.source_path is None:
            try:
                self.source_path = grammar.name  # type: ignore[union-attr]
            except AttributeError:
                self.source_path = '<string>'
        else:
            self.source_path = self.options.source_path

        # Drain file-like objects to get their contents
        try:
            read = grammar.read  # type: ignore[union-attr]
        except AttributeError:
            pass
        else:
            grammar = read()

        cache_fn = None
        cache_sha256 = None
        if isinstance(grammar, str):
            self.source_grammar = grammar
            if self.options.use_bytes:
                if not grammar.isascii():
                    raise ConfigurationError("Grammar must be ascii only, when use_bytes=True")

            if self.options.cache:
                result = resolve_cache_fn(self.options, grammar, options)
                if result is not None:
                    cache_fn, cache_sha256 = result

                    if load_from_cache(self, cache_fn, cache_sha256, options):
                        return

            # Parse the grammar file and compose the grammars
            self.grammar, used_files = load_grammar(grammar, self.source_path, self.options.import_paths, self.options.keep_all_tokens)
        else:
            assert isinstance(grammar, Grammar)
            self.grammar = grammar


        if self.options.lexer == 'auto':
            if self.options.parser == 'lalr':
                self.options.lexer = 'contextual'
            elif self.options.parser == 'earley':
                if self.options.postlex is not None:
                    logger.info("postlex can't be used with the dynamic lexer, so we use 'basic' instead. "
                                "Consider using lalr with contextual instead of earley")
                    self.options.lexer = 'basic'
                else:
                    self.options.lexer = 'dynamic'
            elif self.options.parser == 'cyk':
                self.options.lexer = 'basic'
            else:
                assert False, self.options.parser
        lexer = self.options.lexer
        if isinstance(lexer, type):
            assert issubclass(lexer, Lexer)     # XXX Is this really important? Maybe just ensure interface compliance
        else:
            assert_config(lexer, ('basic', 'contextual', 'dynamic', 'dynamic_complete'))
            if self.options.postlex is not None and 'dynamic' in lexer:
                raise ConfigurationError("Can't use postlex with a dynamic lexer. Use basic or contextual instead")

        if self.options.ambiguity == 'auto':
            if self.options.parser == 'earley':
                self.options.ambiguity = 'resolve'
        else:
            assert_config(self.options.parser, ('earley', 'cyk'), "%r doesn't support disambiguation. Use one of these parsers instead: %s")

        if self.options.priority == 'auto':
            self.options.priority = 'normal'

        if self.options.priority not in _VALID_PRIORITY_OPTIONS:
            raise ConfigurationError("invalid priority option: %r. Must be one of %r" % (self.options.priority, _VALID_PRIORITY_OPTIONS))
        if self.options.ambiguity not in _VALID_AMBIGUITY_OPTIONS:
            raise ConfigurationError("invalid ambiguity option: %r. Must be one of %r" % (self.options.ambiguity, _VALID_AMBIGUITY_OPTIONS))

        if self.options.parser is None:
            terminals_to_keep = '*'     # For lexer-only mode, keep all terminals
        elif self.options.postlex is not None:
            terminals_to_keep = set(self.options.postlex.always_accept)
        else:
            terminals_to_keep = set()

        # Compile the EBNF grammar into BNF
        self.terminals, self.rules, self.ignore_tokens = self.grammar.compile(self.options.start, terminals_to_keep)

        if self.options.edit_terminals:
            for t in self.terminals:
                self.options.edit_terminals(t)

        self._terminals_dict = {t.name: t for t in self.terminals}

        # If the user asked to invert the priorities, negate them all here.
        if self.options.priority == 'invert':
            for rule in self.rules:
                if rule.options.priority is not None:
                    rule.options.priority = -rule.options.priority
            for term in self.terminals:
                term.priority = -term.priority
        # Else, if the user asked to disable priorities, strip them from the
        # rules and terminals. This allows the Earley parsers to skip an extra forest walk
        # for improved performance, if you don't need them (or didn't specify any).
        elif self.options.priority is None:
            for rule in self.rules:
                if rule.options.priority is not None:
                    rule.options.priority = None
            for term in self.terminals:
                term.priority = 0

        # TODO Deprecate lexer_callbacks?
        self.lexer_conf = LexerConf(
                self.terminals, re_module, self.ignore_tokens, self.options.postlex,
                self.options.lexer_callbacks, self.options.g_regex_flags, use_bytes=self.options.use_bytes, strict=self.options.strict
            )

        if self.options.parser:
            self.parser = self._build_parser()
        elif lexer:
            self.lexer = self._build_lexer()

        if cache_fn:
            save_to_cache(cache_fn, cache_sha256, self, used_files)

    if __doc__:
        __doc__ += "\n\n" + LarkOptions.OPTIONS_DOC

    def _build_lexer(self, dont_ignore: bool=False) -> BasicLexer:
        lexer_conf = self.lexer_conf
        if dont_ignore:
            from copy import copy
            lexer_conf = copy(lexer_conf)
            lexer_conf.ignore = ()
        return BasicLexer(lexer_conf)

    def _prepare_callbacks(self) -> None:
        self._callbacks = {}
        # we don't need these callbacks if we aren't building a tree
        if self.options.ambiguity != 'forest':
            self._parse_tree_builder = ParseTreeBuilder(
                    self.rules,
                    self.options.tree_class or Tree,
                    self.options.propagate_positions,
                    self.options.parser != 'lalr' and self.options.ambiguity == 'explicit',
                    self.options.maybe_placeholders
                )
            self._callbacks = self._parse_tree_builder.create_callback(self.options.transformer)
        self._callbacks.update(_get_lexer_callbacks(self.options.transformer, self.terminals))

    def _build_parser(self) -> "ParsingFrontend":
        self._prepare_callbacks()
        _validate_frontend_args(self.options.parser, self.options.lexer)
        parser_conf = ParserConf(self.rules, self._callbacks, self.options.start)
        return _construct_parsing_frontend(
            self.options.parser,
            self.options.lexer,
            self.lexer_conf,
            parser_conf,
            options=self.options
        )

    def save(self, f, exclude_options: Collection[str] = ()) -> None:
        """Saves the instance into the given file object

        Useful for caching and multiprocessing.
        """
        lark_save(self, f, exclude_options)

    @classmethod
    def load(cls: Type[_T], f) -> _T:
        """Loads an instance from the given file object

        Useful for caching and multiprocessing.
        """
        return lark_load(cls, f)

    def _deserialize_lexer_conf(self, data: Dict[str, Any], memo: Dict[int, Union[TerminalDef, Rule]], options: LarkOptions) -> LexerConf:
        return lark_deserialize_lexer_conf(data, memo, options)

    def _load(self: _T, f: Any, **kwargs) -> _T:
        return lark_load_into(self, f, **kwargs)

    @classmethod
    def _load_from_dict(cls, data, memo, **kwargs):
        return lark_load_from_dict(cls, data, memo, **kwargs)

    @overload
    @classmethod
    def open(
        cls,
        grammar_filename: str,
        rel_to: Optional[str] = None,
        *,
        transformer: 'Transformer[Token, _Return_T]',
        **options: Any,
    ) -> 'Lark[_Return_T]': ...

    @overload
    @classmethod
    def open(
        cls,
        grammar_filename: str,
        rel_to: Optional[str] = None,
        **options: Any,
    ) -> 'Lark[ParseTree]': ...

    @classmethod
    def open(cls, grammar_filename: str, rel_to: Optional[str]=None, **options) -> 'Lark':
        """Create an instance of Lark with the grammar given by its filename

        If ``rel_to`` is provided, the function will find the grammar filename in relation to it.

        Example:

            >>> Lark.open("grammar_file.lark", rel_to=__file__, parser="lalr")
            Lark(...)
        """
        if rel_to:
            basepath = os.path.dirname(rel_to)
            grammar_filename = os.path.join(basepath, grammar_filename)
        with open(grammar_filename, encoding='utf8') as f:
            return cls(f, **options)

    @overload
    @classmethod
    def open_from_package(
        cls,
        package: str,
        grammar_path: str,
        search_paths: 'Sequence[str]' = ...,
        *,
        transformer: 'Transformer[Token, _Return_T]',
        **options: Any,
    ) -> 'Lark[_Return_T]': ...

    @overload
    @classmethod
    def open_from_package(
        cls,
        package: str,
        grammar_path: str,
        search_paths: 'Sequence[str]' = ...,
        **options: Any,
    ) -> 'Lark[ParseTree]': ...

    @classmethod
    def open_from_package(cls, package: str, grammar_path: str, search_paths: 'Sequence[str]'=[""], **options) -> 'Lark':
        """Create an instance of Lark with the grammar loaded from within the package ``package``.
        This allows grammar loading from zipapps.

        Imports in the grammar will use the ``package`` and ``search_paths`` provided, through ``FromPackageLoader``

        Example:

            Lark.open_from_package(__name__, "example.lark", ("grammars",), parser=...)
        """
        package_loader = FromPackageLoader(package, search_paths)
        full_path, text = package_loader(None, grammar_path)
        options.setdefault('source_path', full_path)
        options.setdefault('import_paths', [])
        options['import_paths'].append(package_loader)
        return cls(text, **options)

    def __repr__(self):
        return 'Lark(open(%r), parser=%r, lexer=%r, ...)' % (self.source_path, self.options.parser, self.options.lexer)


    def lex(self, text: TextOrSlice, dont_ignore: bool=False) -> Iterator[Token]:
        """Only lex (and postlex) the text, without parsing it. Only relevant when lexer='basic'

        When dont_ignore=True, the lexer will return all tokens, even those marked for %ignore.

        :raises UnexpectedCharacters: In case the lexer cannot find a suitable match.
        """
        lexer: Lexer
        if not hasattr(self, 'lexer') or dont_ignore:
            lexer = self._build_lexer(dont_ignore)
        else:
            lexer = self.lexer
        lexer_thread = LexerThread.from_text(lexer, text)
        stream = lexer_thread.lex(None)
        if self.options.postlex:
            return self.options.postlex.process(stream)
        return stream

    def get_terminal(self, name: str) -> TerminalDef:
        """Get information about a terminal"""
        return self._terminals_dict[name]

    def parse_interactive(self, text: Optional[LarkInput]=None, start: Optional[str]=None) -> 'InteractiveParser':
        """Start an interactive parsing session. Only works when parser='lalr'.

        Parameters:
            text (LarkInput, optional): Text to be parsed. Required for ``resume_parse()``.
            start (str, optional): Start symbol

        Returns:
            A new InteractiveParser instance.

        See Also: ``Lark.parse()``
        """
        return self.parser.parse_interactive(text, start=start)

    def parse(self, text: LarkInput, start: Optional[str]=None, on_error: 'Optional[Callable[[UnexpectedInput], bool]]'=None) -> _Return_T:
        """Parse the given text, according to the options provided.

        Parameters:
            text (LarkInput): Text to be parsed, as `str` or `bytes`.
                TextSlice may also be used, but only when lexer='basic' or 'contextual'.
                If Lark was created with a custom lexer, this may be an object of any type.
            start (str, optional): Required if Lark was given multiple possible start symbols (using the start option).
            on_error (function, optional): if provided, will be called on UnexpectedInput error,
                with the exception as its argument. Return true to resume parsing, or false to raise the exception.
                LALR only. See examples/advanced/error_handling.py for an example of how to use on_error.

        Returns:
            If a transformer is supplied to ``__init__``, returns whatever is the
            result of the transformation. Otherwise, returns a Tree instance.

        :raises UnexpectedInput: On a parse error, one of these sub-exceptions will rise:
                ``UnexpectedCharacters``, ``UnexpectedToken``, or ``UnexpectedEOF``.
                For convenience, these sub-exceptions also inherit from ``ParserError`` and ``LexerError``.

        """
        if on_error is not None and self.options.parser != 'lalr':
            raise NotImplementedError("The on_error option is only implemented for the LALR(1) parser.")
        return self.parser.parse(text, start=start, on_error=on_error)


###}
