from __future__ import absolute_import

import sys, os, pickle, hashlib, logging
from io import open


from .utils import STRING_TYPE, Serialize, SerializeMemoizer, FS
from .load_grammar import load_grammar
from .tree import Tree
from .common import LexerConf, ParserConf

from .lexer import Lexer, TraditionalLexer, TerminalDef, UnexpectedToken
from .parse_tree_builder import ParseTreeBuilder
from .parser_frontends import get_frontend
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
# General

    start - The start symbol. Either a string, or a list of strings for
            multiple possible starts (Default: "start")
    debug - Display debug information, such as warnings (default: False)
    transformer - Applies the transformer to every parse tree (equivlent to
                  applying it after the parse, but faster)
    propagate_positions - Propagates (line, column, end_line, end_column)
                          attributes into all tree branches.
    maybe_placeholders - When True, the `[]` operator returns `None` when not matched.
                         When `False`,  `[]` behaves like the `?` operator,
                             and returns no value at all.
                         (default=`False`. Recommended to set to `True`)
    regex - When True, uses the `regex` module instead of the stdlib `re`.
    cache - Cache the results of the Lark grammar analysis, for x2 to x3 faster loading.
            LALR only for now.
        When `False`, does nothing (default)
        When `True`, caches to a temporary file in the local directory
        When given a string, caches to the path pointed by the string

    g_regex_flags - Flags that are applied to all terminals
                    (both regex and strings)
    keep_all_tokens - Prevent the tree builder from automagically
                      removing "punctuation" tokens (default: False)

# Algorithm

    parser - Decides which parser engine to use
             Accepts "earley" or "lalr". (Default: "earley")
             (there is also a "cyk" option for legacy)

    lexer - Decides whether or not to use a lexer stage
        "auto" (default): Choose for me based on the parser
        "standard": Use a standard lexer
        "contextual": Stronger lexer (only works with parser="lalr")
        "dynamic": Flexible and powerful (only with parser="earley")
        "dynamic_complete": Same as dynamic, but tries *every* variation
                            of tokenizing possible.

    ambiguity - Decides how to handle ambiguity in the parse.
                Only relevant if parser="earley"
        "resolve": The parser will automatically choose the simplest
                    derivation (it chooses consistently: greedy for
                    tokens, non-greedy for rules)
        "explicit": The parser will return all derivations wrapped
                    in "_ambig" tree nodes (i.e. a forest).

# Domain Specific

    postlex - Lexer post-processing (Default: None) Only works with the
                standard and contextual lexers.
    priority - How priorities should be evaluated - auto, none, normal,
                invert (Default: auto)
    lexer_callbacks - Dictionary of callbacks for the lexer. May alter
                        tokens during lexing. Use with caution.
    edit_terminals - A callback
    """
    if __doc__:
        __doc__ += OPTIONS_DOC

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
    }

    def __init__(self, options_dict):
        o = dict(options_dict)

        options = {}
        for name, default in self._defaults.items():
            if name in o:
                value = o.pop(name)
                if isinstance(default, bool) and name != 'cache':
                    value = bool(value)
            else:
                value = default

            options[name] = value

        if isinstance(options['start'], STRING_TYPE):
            options['start'] = [options['start']]

        self.__dict__['options'] = options

        assert self.parser in ('earley', 'lalr', 'cyk', None)

        if self.parser == 'earley' and self.transformer:
            raise ValueError('Cannot specify an embedded transformer when using the Earley algorithm.'
                             'Please use your transformer on the resulting parse tree, or use a different algorithm (i.e. LALR)')

        if o:
            raise ValueError("Unknown options: %s" % o.keys())

    def __getattr__(self, name):
        try:
            return self.options[name]
        except KeyError as e:
            raise AttributeError(e)

    def __setattr__(self, name, value):
        assert name in self.options
        self.options[name] = value

    def serialize(self, memo):
        return self.options

    @classmethod
    def deserialize(cls, data, memo):
        return cls(data)


class Lark(Serialize):
    def __init__(self, grammar, **options):
        """
            grammar : a string or file-object containing the grammar spec (using Lark's ebnf syntax)
            options : a dictionary controlling various aspects of Lark.
        """

        self.options = LarkOptions(options)

        # Set regex or re module
        use_regex = self.options.regex
        if use_regex:
            if regex:
                self.re = regex
            else:
                raise ImportError('`regex` module must be installed if calling `Lark(regex=True)`.')
        else:
            self.re = re

        # Some, but not all file-like objects have a 'name' attribute
        try:
            self.source = grammar.name
        except AttributeError:
            self.source = '<string>'

        # Drain file-like objects to get their contents
        try:
            read = grammar.read
        except AttributeError:
            pass
        else:
            grammar = read()

        assert isinstance(grammar, STRING_TYPE)

        cache_fn = None
        if self.options.cache:
            if self.options.parser != 'lalr':
                raise NotImplementedError("cache only works with parser='lalr' for now")
            if isinstance(self.options.cache, STRING_TYPE):
                cache_fn = self.options.cache
            else:
                if self.options.cache is not True:
                    raise ValueError("cache must be bool or str")
                unhashable = ('transformer', 'postlex', 'lexer_callbacks', 'edit_terminals')
                from . import __version__
                options_str = ''.join(k+str(v) for k, v in options.items() if k not in unhashable)
                s = grammar + options_str + __version__
                md5 = hashlib.md5(s.encode()).hexdigest()
                cache_fn = '.lark_cache_%s.tmp' % md5

            if FS.exists(cache_fn):
                logging.debug('Loading grammar from cache: %s', cache_fn)
                with FS.open(cache_fn, 'rb') as f:
                    self._load(f, self.options.transformer, self.options.postlex)
                return

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
        assert lexer in ('standard', 'contextual', 'dynamic', 'dynamic_complete') or issubclass(lexer, Lexer)

        if self.options.ambiguity == 'auto':
            if self.options.parser == 'earley':
                self.options.ambiguity = 'resolve'
        else:
            disambig_parsers = ['earley', 'cyk']
            assert self.options.parser in disambig_parsers, (
                'Only %s supports disambiguation right now') % ', '.join(disambig_parsers)

        if self.options.priority == 'auto':
            if self.options.parser in ('earley', 'cyk', ):
                self.options.priority = 'normal'
            elif self.options.parser in ('lalr', ):
                self.options.priority = None
        elif self.options.priority in ('invert', 'normal'):
            assert self.options.parser in ('earley', 'cyk'), "priorities are not supported for LALR at this time"

        assert self.options.priority in ('auto', None, 'normal', 'invert'), 'invalid priority option specified: {}. options are auto, none, normal, invert.'.format(self.options.priority)
        assert self.options.ambiguity not in ('resolve__antiscore_sum', ), 'resolve__antiscore_sum has been replaced with the option priority="invert"'
        assert self.options.ambiguity in ('resolve', 'explicit', 'auto', )

        # Parse the grammar file and compose the grammars (TODO)
        self.grammar = load_grammar(grammar, self.source, self.re)

        # Compile the EBNF grammar into BNF
        self.terminals, self.rules, self.ignore_tokens = self.grammar.compile(self.options.start)

        if self.options.edit_terminals:
            for t in self.terminals:
                self.options.edit_terminals(t)

        self._terminals_dict = {t.name:t for t in self.terminals}

        # If the user asked to invert the priorities, negate them all here.
        # This replaces the old 'resolve__antiscore_sum' option.
        if self.options.priority == 'invert':
            for rule in self.rules:
                if rule.options.priority is not None:
                    rule.options.priority = -rule.options.priority
        # Else, if the user asked to disable priorities, strip them from the
        # rules. This allows the Earley parsers to skip an extra forest walk
        # for improved performance, if you don't need them (or didn't specify any).
        elif self.options.priority == None:
            for rule in self.rules:
                if rule.options.priority is not None:
                    rule.options.priority = None

        # TODO Deprecate lexer_callbacks?
        lexer_callbacks = dict(self.options.lexer_callbacks)
        if self.options.transformer:
            t = self.options.transformer
            for term in self.terminals:
                if hasattr(t, term.name):
                    lexer_callbacks[term.name] = getattr(t, term.name)

        self.lexer_conf = LexerConf(self.terminals, self.ignore_tokens, self.options.postlex, lexer_callbacks, self.options.g_regex_flags)

        if self.options.parser:
            self.parser = self._build_parser()
        elif lexer:
            self.lexer = self._build_lexer()

        if cache_fn:
            logging.debug('Saving grammar to cache: %s', cache_fn)
            with FS.open(cache_fn, 'wb') as f:
                self.save(f)

    if __init__.__doc__:
        __init__.__doc__ += "\nOptions:\n" + LarkOptions.OPTIONS_DOC

    __serialize_fields__ = 'parser', 'rules', 'options'

    def _build_lexer(self):
        return TraditionalLexer(self.lexer_conf.tokens, ignore=self.lexer_conf.ignore, user_callbacks=self.lexer_conf.callbacks, g_regex_flags=self.lexer_conf.g_regex_flags)

    def _prepare_callbacks(self):
        self.parser_class = get_frontend(self.options.parser, self.options.lexer)
        self._parse_tree_builder = ParseTreeBuilder(self.rules, self.options.tree_class or Tree, self.options.propagate_positions, self.options.keep_all_tokens, self.options.parser!='lalr' and self.options.ambiguity=='explicit', self.options.maybe_placeholders)
        self._callbacks = self._parse_tree_builder.create_callback(self.options.transformer)

    def _build_parser(self):
        self._prepare_callbacks()
        parser_conf = ParserConf(self.rules, self._callbacks, self.options.start)
        return self.parser_class(self.lexer_conf, parser_conf, self.re, options=self.options)

    def save(self, f):
        data, m = self.memo_serialize([TerminalDef, Rule])
        pickle.dump({'data': data, 'memo': m}, f)

    @classmethod
    def load(cls, f):
        inst = cls.__new__(cls)
        return inst._load(f)

    def _load(self, f, transformer=None, postlex=None):
        if isinstance(f, dict):
            d = f
        else:
            d = pickle.load(f)
        memo = d['memo']
        data = d['data']

        assert memo
        memo = SerializeMemoizer.deserialize(memo, {'Rule': Rule, 'TerminalDef': TerminalDef}, {})
        options = dict(data['options'])
        if transformer is not None:
            options['transformer'] = transformer
        if postlex is not None:
            options['postlex'] = postlex
        self.options = LarkOptions.deserialize(options, memo)
        self.re = regex if self.options.regex else re
        self.rules = [Rule.deserialize(r, memo) for r in data['rules']]
        self.source = '<deserialized>'
        self._prepare_callbacks()
        self.parser = self.parser_class.deserialize(data['parser'], memo, self._callbacks, self.options.postlex, self.re)
        return self

    @classmethod
    def _load_from_dict(cls, data, memo, transformer=None, postlex=None):
        inst = cls.__new__(cls)
        return inst._load({'data': data, 'memo': memo}, transformer, postlex)

    @classmethod
    def open(cls, grammar_filename, rel_to=None, **options):
        """Create an instance of Lark with the grammar given by its filename

        If rel_to is provided, the function will find the grammar filename in relation to it.

        Example:

            >>> Lark.open("grammar_file.lark", rel_to=__file__, parser="lalr")
            Lark(...)

        """
        if rel_to:
            basepath = os.path.dirname(rel_to)
            grammar_filename = os.path.join(basepath, grammar_filename)
        with open(grammar_filename, encoding='utf8') as f:
            return cls(f, **options)

    def __repr__(self):
        return 'Lark(open(%r), parser=%r, lexer=%r, ...)' % (self.source, self.options.parser, self.options.lexer)


    def lex(self, text):
        "Only lex (and postlex) the text, without parsing it. Only relevant when lexer='standard'"
        if not hasattr(self, 'lexer'):
            self.lexer = self._build_lexer()
        stream = self.lexer.lex(text)
        if self.options.postlex:
            return self.options.postlex.process(stream)
        return stream

    def get_terminal(self, name):
        "Get information about a terminal"
        return self._terminals_dict[name]

    def parse(self, text, start=None, on_error=None):
        """Parse the given text, according to the options provided.

        Parameters:
            start: str - required if Lark was given multiple possible start symbols (using the start option).
            on_error: function - if provided, will be called on UnexpectedToken error. Return true to resume parsing. LALR only.

        Returns a tree, unless specified otherwise.
        """
        try:
            return self.parser.parse(text, start=start)
        except UnexpectedToken as e:
            if on_error is None:
                raise

            while True:
                if not on_error(e):
                    raise e
                try:
                    return e.puppet.resume_parse()
                except UnexpectedToken as e2:
                    e = e2


###}
