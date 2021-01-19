from __future__ import absolute_import
from lark.exceptions import UnexpectedCharacters, UnexpectedInput, UnexpectedToken, ConfigurationError, assert_config

import sys, os, pickle, hashlib
from io import open
import tempfile
from warnings import warn

from .utils import STRING_TYPE, Serialize, SerializeMemoizer, FS, isascii, logger
from .load_grammar import load_grammar, FromPackageLoader, Grammar
from .tree import Tree
from .common import LexerConf, ParserConf

from .lexer import Lexer, TraditionalLexer, TerminalDef, LexerThread
from .parse_tree_builder import ParseTreeBuilder
from .parser_frontends import get_frontend, _get_lexer_callbacks
from .grammar import Rule

import re
try:
    import regex
except ImportError:
    regex = None

###{standalone


class LarkOptions(Serialize):
    """Specifies the options for Lark

    """
    OPTIONS_DOC = """
    **===  General Options  ===**

    start
            The start symbol. Either a string, or a list of strings for multiple possible starts (Default: "start")
    debug
            Display debug information and extra warnings. Use only when debugging (default: False)
            When used with Earley, it generates a forest graph as "sppf.png", if 'dot' is installed.
    transformer
            Applies the transformer to every parse tree (equivalent to applying it after the parse, but faster)
    propagate_positions
            Propagates (line, column, end_line, end_column) attributes into all tree branches.
    maybe_placeholders
            When True, the ``[]`` operator returns ``None`` when not matched.

            When ``False``,  ``[]`` behaves like the ``?`` operator, and returns no value at all.
            (default= ``False``. Recommended to set to ``True``)
    cache
            Cache the results of the Lark grammar analysis, for x2 to x3 faster loading. LALR only for now.

            - When ``False``, does nothing (default)
            - When ``True``, caches to a temporary file in the local directory
            - When given a string, caches to the path pointed by the string
    regex
            When True, uses the ``regex`` module instead of the stdlib ``re``.
    g_regex_flags
            Flags that are applied to all terminals (both regex and strings)
    keep_all_tokens
            Prevent the tree builder from automagically removing "punctuation" tokens (default: False)
    tree_class
            Lark will produce trees comprised of instances of this class instead of the default ``lark.Tree``.

    **=== Algorithm Options ===**

    parser
            Decides which parser engine to use. Accepts "earley" or "lalr". (Default: "earley").
            (there is also a "cyk" option for legacy)
    lexer
            Decides whether or not to use a lexer stage

            - "auto" (default): Choose for me based on the parser
            - "standard": Use a standard lexer
            - "contextual": Stronger lexer (only works with parser="lalr")
            - "dynamic": Flexible and powerful (only with parser="earley")
            - "dynamic_complete": Same as dynamic, but tries *every* variation of tokenizing possible.
    ambiguity
            Decides how to handle ambiguity in the parse. Only relevant if parser="earley"

            - "resolve": The parser will automatically choose the simplest derivation
              (it chooses consistently: greedy for tokens, non-greedy for rules)
            - "explicit": The parser will return all derivations wrapped in "_ambig" tree nodes (i.e. a forest).
            - "forest": The parser will return the root of the shared packed parse forest.

    **=== Misc. / Domain Specific Options ===**

    postlex
            Lexer post-processing (Default: None) Only works with the standard and contextual lexers.
    priority
            How priorities should be evaluated - auto, none, normal, invert (Default: auto)
    lexer_callbacks
            Dictionary of callbacks for the lexer. May alter tokens during lexing. Use with caution.
    use_bytes
            Accept an input of type ``bytes`` instead of ``str`` (Python 3 only).
    edit_terminals
            A callback for editing the terminals before parse.
    import_paths
            A List of either paths or loader functions to specify from where grammars are imported
    source_path
            Override the source of from where the grammar was loaded. Useful for relative imports and unconventional grammar loading

    **=== End Options ===**
    """
    if __doc__:
        __doc__ += OPTIONS_DOC


    # Adding a new option needs to be done in multiple places:
    # - In the dictionary below. This is the primary truth of which options `Lark.__init__` accepts
    # - In the docstring above. It is used both for the docstring of `LarkOptions` and `Lark`, and in readthedocs
    # - In `lark-stubs/lark.pyi`:
    #   - As attribute to `LarkOptions`
    #   - As parameter to `Lark.__init__`
    # - Potentially in `_LOAD_ALLOWED_OPTIONS` below this class, when the option doesn't change how the grammar is loaded
    # - Potentially in `lark.tools.__init__`, if it makes sense, and it can easily be passed as a cmd argument
    _defaults = {
        'debug': False,
        'keep_all_tokens': False,
        'tree_class': None,
        'cache': False,
        'postlex': None,
        'parser': 'earley',
        'lexer': 'auto',
        'transformer': None,
        'start': 'start',
        'priority': 'auto',
        'ambiguity': 'auto',
        'regex': False,
        'propagate_positions': False,
        'lexer_callbacks': {},
        'maybe_placeholders': False,
        'edit_terminals': None,
        'g_regex_flags': 0,
        'use_bytes': False,
        'import_paths': [],
        'source_path': None,
    }

    def __init__(self, options_dict):
        o = dict(options_dict)

        options = {}
        for name, default in self._defaults.items():
            if name in o:
                value = o.pop(name)
                if isinstance(default, bool) and name not in ('cache', 'use_bytes'):
                    value = bool(value)
            else:
                value = default

            options[name] = value

        if isinstance(options['start'], STRING_TYPE):
            options['start'] = [options['start']]

        self.__dict__['options'] = options


        assert_config(self.parser, ('earley', 'lalr', 'cyk', None))

        if self.parser == 'earley' and self.transformer:
            raise ConfigurationError('Cannot specify an embedded transformer when using the Earley algorithm.'
                             'Please use your transformer on the resulting parse tree, or use a different algorithm (i.e. LALR)')

        if o:
            raise ConfigurationError("Unknown options: %s" % o.keys())

    def __getattr__(self, name):
        try:
            return self.options[name]
        except KeyError as e:
            raise AttributeError(e)

    def __setattr__(self, name, value):
        assert_config(name, self.options.keys(), "%r isn't a valid option. Expected one of: %s")
        self.options[name] = value

    def serialize(self, memo):
        return self.options

    @classmethod
    def deserialize(cls, data, memo):
        return cls(data)


# Options that can be passed to the Lark parser, even when it was loaded from cache/standalone.
# These option are only used outside of `load_grammar`.
_LOAD_ALLOWED_OPTIONS = {'postlex', 'transformer', 'use_bytes', 'debug', 'g_regex_flags', 'regex', 'propagate_positions', 'tree_class'}

_VALID_PRIORITY_OPTIONS = ('auto', 'normal', 'invert', None)
_VALID_AMBIGUITY_OPTIONS = ('auto', 'resolve', 'explicit', 'forest')


class Lark(Serialize):
    """Main interface for the library.

    It's mostly a thin wrapper for the many different parsers, and for the tree constructor.

    Parameters:
        grammar: a string or file-object containing the grammar spec (using Lark's ebnf syntax)
        options: a dictionary controlling various aspects of Lark.

    Example:
        >>> Lark(r'''start: "foo" ''')
        Lark(...)
    """
    def __init__(self, grammar, **options):
        self.options = LarkOptions(options)

        # Set regex or re module
        use_regex = self.options.regex
        if use_regex:
            if regex:
                re_module = regex
            else:
                raise ImportError('`regex` module must be installed if calling `Lark(regex=True)`.')
        else:
            re_module = re

        # Some, but not all file-like objects have a 'name' attribute
        if self.options.source_path is None:
            try:
                self.source_path = grammar.name
            except AttributeError:
                self.source_path = '<string>'
        else:
            self.source_path = self.options.source_path

        # Drain file-like objects to get their contents
        try:
            read = grammar.read
        except AttributeError:
            pass
        else:
            grammar = read()

        cache_fn = None
        if isinstance(grammar, STRING_TYPE):
            self.source_grammar = grammar
            if self.options.use_bytes:
                if not isascii(grammar):
                    raise ConfigurationError("Grammar must be ascii only, when use_bytes=True")
                if sys.version_info[0] == 2 and self.options.use_bytes != 'force':
                    raise ConfigurationError("`use_bytes=True` may have issues on python2."
                                              "Use `use_bytes='force'` to use it at your own risk.")
    
            if self.options.cache:
                if self.options.parser != 'lalr':
                    raise ConfigurationError("cache only works with parser='lalr' for now")
                if isinstance(self.options.cache, STRING_TYPE):
                    cache_fn = self.options.cache
                else:
                    if self.options.cache is not True:
                        raise ConfigurationError("cache argument must be bool or str")
                    unhashable = ('transformer', 'postlex', 'lexer_callbacks', 'edit_terminals')
                    from . import __version__
                    options_str = ''.join(k+str(v) for k, v in options.items() if k not in unhashable)
                    s = grammar + options_str + __version__
                    md5 = hashlib.md5(s.encode()).hexdigest()
                    cache_fn = tempfile.gettempdir() + '/.lark_cache_%s.tmp' % md5
    
                if FS.exists(cache_fn):
                    logger.debug('Loading grammar from cache: %s', cache_fn)
                    # Remove options that aren't relevant for loading from cache
                    for name in (set(options) - _LOAD_ALLOWED_OPTIONS):
                        del options[name]
                    with FS.open(cache_fn, 'rb') as f:
                        try:
                            self._load(f, **options)
                        except Exception:
                            raise RuntimeError("Failed to load Lark from cache: %r. Try to delete the file and run again." % cache_fn)
                    return


            # Parse the grammar file and compose the grammars
            self.grammar = load_grammar(grammar, self.source_path, self.options.import_paths, self.options.keep_all_tokens)
        else:
            assert isinstance(grammar, Grammar)
            self.grammar = grammar
            

        if self.options.lexer == 'auto':
            if self.options.parser == 'lalr':
                self.options.lexer = 'contextual'
            elif self.options.parser == 'earley':
                self.options.lexer = 'dynamic'
            elif self.options.parser == 'cyk':
                self.options.lexer = 'standard'
            else:
                assert False, self.options.parser
        lexer = self.options.lexer
        if isinstance(lexer, type):
            assert issubclass(lexer, Lexer)     # XXX Is this really important? Maybe just ensure interface compliance
        else:
            assert_config(lexer, ('standard', 'contextual', 'dynamic', 'dynamic_complete'))

        if self.options.ambiguity == 'auto':
            if self.options.parser == 'earley':
                self.options.ambiguity = 'resolve'
        else:
            assert_config(self.options.parser, ('earley', 'cyk'), "%r doesn't support disambiguation. Use one of these parsers instead: %s")

        if self.options.priority == 'auto':
            self.options.priority = 'normal'

        if self.options.priority not in _VALID_PRIORITY_OPTIONS:
            raise ConfigurationError("invalid priority option: %r. Must be one of %r" % (self.options.priority, _VALID_PRIORITY_OPTIONS))
        assert self.options.ambiguity not in ('resolve__antiscore_sum', ), 'resolve__antiscore_sum has been replaced with the option priority="invert"'
        if self.options.ambiguity not in _VALID_AMBIGUITY_OPTIONS:
            raise ConfigurationError("invalid ambiguity option: %r. Must be one of %r" % (self.options.ambiguity, _VALID_AMBIGUITY_OPTIONS))

        if self.options.postlex is not None:
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
        # This replaces the old 'resolve__antiscore_sum' option.
        if self.options.priority == 'invert':
            for rule in self.rules:
                if rule.options.priority is not None:
                    rule.options.priority = -rule.options.priority
        # Else, if the user asked to disable priorities, strip them from the
        # rules. This allows the Earley parsers to skip an extra forest walk
        # for improved performance, if you don't need them (or didn't specify any).
        elif self.options.priority is None:
            for rule in self.rules:
                if rule.options.priority is not None:
                    rule.options.priority = None

        # TODO Deprecate lexer_callbacks?
        lexer_callbacks = (_get_lexer_callbacks(self.options.transformer, self.terminals)
                           if self.options.transformer
                           else {})
        lexer_callbacks.update(self.options.lexer_callbacks)

        self.lexer_conf = LexerConf(self.terminals, re_module, self.ignore_tokens, self.options.postlex, lexer_callbacks, self.options.g_regex_flags, use_bytes=self.options.use_bytes)

        if self.options.parser:
            self.parser = self._build_parser()
        elif lexer:
            self.lexer = self._build_lexer()

        if cache_fn:
            logger.debug('Saving grammar to cache: %s', cache_fn)
            with FS.open(cache_fn, 'wb') as f:
                self.save(f)

    if __doc__:
        __doc__ += "\n\n" + LarkOptions.OPTIONS_DOC

    __serialize_fields__ = 'parser', 'rules', 'options'

    def _build_lexer(self, dont_ignore=False):
        lexer_conf = self.lexer_conf
        if dont_ignore:
            from copy import copy
            lexer_conf = copy(lexer_conf)
            lexer_conf.ignore = ()
        return TraditionalLexer(lexer_conf)

    def _prepare_callbacks(self):
        self.parser_class = get_frontend(self.options.parser, self.options.lexer)
        self._callbacks = None
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

    def _build_parser(self):
        self._prepare_callbacks()
        parser_conf = ParserConf(self.rules, self._callbacks, self.options.start)
        return self.parser_class(self.lexer_conf, parser_conf, options=self.options)

    def save(self, f):
        """Saves the instance into the given file object

        Useful for caching and multiprocessing.
        """
        data, m = self.memo_serialize([TerminalDef, Rule])
        pickle.dump({'data': data, 'memo': m}, f, protocol=pickle.HIGHEST_PROTOCOL)

    @classmethod
    def load(cls, f):
        """Loads an instance from the given file object

        Useful for caching and multiprocessing.
        """
        inst = cls.__new__(cls)
        return inst._load(f)

    def _load(self, f, **kwargs):
        if isinstance(f, dict):
            d = f
        else:
            d = pickle.load(f)
        memo = d['memo']
        data = d['data']

        assert memo
        memo = SerializeMemoizer.deserialize(memo, {'Rule': Rule, 'TerminalDef': TerminalDef}, {})
        options = dict(data['options'])
        if (set(kwargs) - _LOAD_ALLOWED_OPTIONS) & set(LarkOptions._defaults):
            raise ConfigurationError("Some options are not allowed when loading a Parser: {}"
                             .format(set(kwargs) - _LOAD_ALLOWED_OPTIONS))
        options.update(kwargs)
        self.options = LarkOptions.deserialize(options, memo)
        self.rules = [Rule.deserialize(r, memo) for r in data['rules']]
        self.source_path = '<deserialized>'
        self._prepare_callbacks()
        self.parser = self.parser_class.deserialize(
            data['parser'],
            memo,
            self._callbacks,
            self.options,  # Not all, but multiple attributes are used
        )
        self.lexer_conf = self.parser.lexer_conf
        self.terminals = self.parser.lexer_conf.terminals
        self._terminals_dict = {t.name: t for t in self.terminals}
        return self

    @classmethod
    def _load_from_dict(cls, data, memo, **kwargs):
        inst = cls.__new__(cls)
        return inst._load({'data': data, 'memo': memo}, **kwargs)

    @classmethod
    def open(cls, grammar_filename, rel_to=None, **options):
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

    @classmethod
    def open_from_package(cls, package, grammar_path, search_paths=("",), **options):
        """Create an instance of Lark with the grammar loaded from within the package `package`.
        This allows grammar loading from zipapps.

        Imports in the grammar will use the `package` and `search_paths` provided, through `FromPackageLoader`

        Example:

            Lark.open_from_package(__name__, "example.lark", ("grammars",), parser=...)
        """
        package = FromPackageLoader(package, search_paths)
        full_path, text = package(None, grammar_path)
        options.setdefault('source_path', full_path)
        options.setdefault('import_paths', [])
        options['import_paths'].append(package)
        return cls(text, **options)

    def __repr__(self):
        return 'Lark(open(%r), parser=%r, lexer=%r, ...)' % (self.source_path, self.options.parser, self.options.lexer)


    def lex(self, text, dont_ignore=False):
        """Only lex (and postlex) the text, without parsing it. Only relevant when lexer='standard'

        When dont_ignore=True, the lexer will return all tokens, even those marked for %ignore.
        """
        if not hasattr(self, 'lexer') or dont_ignore:
            lexer = self._build_lexer(dont_ignore)
        else:
            lexer = self.lexer
        lexer_thread = LexerThread(lexer, text)
        stream = lexer_thread.lex(None)
        if self.options.postlex:
            return self.options.postlex.process(stream)
        return stream

    def get_terminal(self, name):
        "Get information about a terminal"
        return self._terminals_dict[name]

    def parse(self, text, start=None, on_error=None):
        """Parse the given text, according to the options provided.

        Parameters:
            text (str): Text to be parsed.
            start (str, optional): Required if Lark was given multiple possible start symbols (using the start option).
            on_error (function, optional): if provided, will be called on UnexpectedToken error. Return true to resume parsing.
                LALR only. See examples/advanced/error_puppet.py for an example of how to use on_error.

        Returns:
            If a transformer is supplied to ``__init__``, returns whatever is the
            result of the transformation. Otherwise, returns a Tree instance.

        """

        try:
            return self.parser.parse(text, start=start)
        except UnexpectedInput as e:
            if on_error is None:
                raise

            while True:
                if isinstance(e, UnexpectedCharacters):
                    s = e.puppet.lexer_state.state
                    p = s.line_ctr.char_pos

                if not on_error(e):
                    raise e

                if isinstance(e, UnexpectedCharacters):
                    # If user didn't change the character position, then we should
                    if p == s.line_ctr.char_pos:
                        s.line_ctr.feed(s.text[p:p+1])

                try:
                    return e.puppet.resume_parse()
                except UnexpectedToken as e2:
                    if isinstance(e, UnexpectedToken) and e.token.type == e2.token.type == '$END' and e.puppet == e2.puppet:
                        # Prevent infinite loop
                        raise e2
                    e = e2
                except UnexpectedCharacters as e2:
                    e = e2

    @property
    def source(self):
        warn("Lark.source attribute has been renamed to Lark.source_path", DeprecationWarning)
        return self.source_path

    @source.setter
    def source(self, value):
        self.source_path = value

    @property
    def grammar_source(self):
        warn("Lark.grammar_source attribute has been renamed to Lark.source_grammar", DeprecationWarning)
        return self.source_grammar

    @grammar_source.setter
    def grammar_source(self, value):
        self.source_grammar = value


###}
