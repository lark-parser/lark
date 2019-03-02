from __future__ import absolute_import

import os
import time
from collections import defaultdict
from io import open

from .utils import STRING_TYPE
from .load_grammar import load_grammar
from .tree import Tree
from .common import LexerConf, ParserConf

from .lexer import Lexer, TraditionalLexer
from .parse_tree_builder import ParseTreeBuilder
from .parser_frontends import get_frontend


class LarkOptions(object):
    """Specifies the options for Lark

    """
    OPTIONS_DOC = """
        parser - Decides which parser engine to use, "earley" or "lalr". (Default: "earley")
                 Note: "lalr" requires a lexer

        lexer - Decides whether or not to use a lexer stage
            "standard": Use a standard lexer
            "contextual": Stronger lexer (only works with parser="lalr")
            "dynamic": Flexible and powerful (only with parser="earley")
            "dynamic_complete": Same as dynamic, but tries *every* variation
                                of tokenizing possible. (only with parser="earley")
            "auto" (default): Choose for me based on grammar and parser

        ambiguity - Decides how to handle ambiguity in the parse. Only relevant if parser="earley"
            "resolve": The parser will automatically choose the simplest derivation
                       (it chooses consistently: greedy for tokens, non-greedy for rules)
            "explicit": The parser will return all derivations wrapped in "_ambig" tree nodes (i.e. a forest).

        transformer - Applies the transformer to every parse tree
        debug - Affects verbosity (default: False)
        keep_all_tokens - Don't automagically remove "punctuation" tokens (default: False)
        cache_grammar - Cache the Lark grammar (Default: False)
        postlex - Lexer post-processing (Default: None) Only works with the standard and contextual lexers.
        start - The start symbol (Default: start)
        profile - Measure run-time usage in Lark. Read results from the profiler proprety (Default: False)
        priority - How priorities should be evaluated - auto, none, normal, invert (Default: auto)
        propagate_positions - Propagates [line, column, end_line, end_column] attributes into all tree branches.
        lexer_callbacks - Dictionary of callbacks for the lexer. May alter tokens during lexing. Use with caution.
        maybe_placeholders - Experimental feature. Instead of omitting optional rules (i.e. rule?), replace them with None
    """
    if __doc__:
        __doc__ += OPTIONS_DOC

    def __init__(self, options_dict):
        o = dict(options_dict)

        self.debug = bool(o.pop('debug', False))
        self.keep_all_tokens = bool(o.pop('keep_all_tokens', False))
        self.tree_class = o.pop('tree_class', Tree)
        self.cache_grammar = o.pop('cache_grammar', False)
        self.postlex = o.pop('postlex', None)
        self.parser = o.pop('parser', 'earley')
        self.lexer = o.pop('lexer', 'auto')
        self.transformer = o.pop('transformer', None)
        self.start = o.pop('start', 'start')
        self.profile = o.pop('profile', False)
        self.priority = o.pop('priority', 'auto')
        self.ambiguity = o.pop('ambiguity', 'auto')
        self.propagate_positions = o.pop('propagate_positions', False)
        self.lexer_callbacks = o.pop('lexer_callbacks', {})
        self.maybe_placeholders = o.pop('maybe_placeholders', False)

        assert self.parser in ('earley', 'lalr', 'cyk', None)

        if self.parser == 'earley' and self.transformer:
            raise ValueError('Cannot specify an embedded transformer when using the Earley algorithm.'
                             'Please use your transformer on the resulting parse tree, or use a different algorithm (i.e. LALR)')

        if o:
            raise ValueError("Unknown options: %s" % o.keys())


class Profiler:
    def __init__(self):
        self.total_time = defaultdict(float)
        self.cur_section = '__init__'
        self.last_enter_time = time.time()

    def enter_section(self, name):
        cur_time = time.time()
        self.total_time[self.cur_section] += cur_time - self.last_enter_time
        self.last_enter_time = cur_time
        self.cur_section = name

    def make_wrapper(self, name, f):
        def wrapper(*args, **kwargs):
            last_section = self.cur_section
            self.enter_section(name)
            try:
                return f(*args, **kwargs)
            finally:
                self.enter_section(last_section)

        return wrapper


class Lark:
    def __init__(self, grammar, **options):
        """
            grammar : a string or file-object containing the grammar spec (using Lark's ebnf syntax)
            options : a dictionary controlling various aspects of Lark.
        """
        self.options = LarkOptions(options)

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

        if self.options.cache_grammar:
            raise NotImplementedError("Not available yet")

        assert not self.options.profile, "Feature temporarily disabled"
        self.profiler = Profiler() if self.options.profile else None

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
        self.grammar = load_grammar(grammar, self.source)

        # Compile the EBNF grammar into BNF
        self.terminals, self.rules, self.ignore_tokens = self.grammar.compile()

        # If the user asked to invert the priorities, negate them all here.
        # This replaces the old 'resolve__antiscore_sum' option.
        if self.options.priority == 'invert':
            for rule in self.rules:
                if rule.options and rule.options.priority is not None:
                    rule.options.priority = -rule.options.priority
        # Else, if the user asked to disable priorities, strip them from the
        # rules. This allows the Earley parsers to skip an extra forest walk
        # for improved performance, if you don't need them (or didn't specify any).
        elif self.options.priority == None:
            for rule in self.rules:
                if rule.options and rule.options.priority is not None:
                    rule.options.priority = None
        self.lexer_conf = LexerConf(self.terminals, self.ignore_tokens, self.options.postlex, self.options.lexer_callbacks)

        if self.options.parser:
            self.parser = self._build_parser()
        elif lexer:
            self.lexer = self._build_lexer()

        if self.profiler: self.profiler.enter_section('outside_lark')

    if __init__.__doc__:
        __init__.__doc__ += "\nOPTIONS:" + LarkOptions.OPTIONS_DOC

    def _build_lexer(self):
        return TraditionalLexer(self.lexer_conf.tokens, ignore=self.lexer_conf.ignore, user_callbacks=self.lexer_conf.callbacks)

    def _build_parser(self):
        self.parser_class = get_frontend(self.options.parser, self.options.lexer)

        self._parse_tree_builder = ParseTreeBuilder(self.rules, self.options.tree_class, self.options.propagate_positions, self.options.keep_all_tokens, self.options.parser!='lalr' and self.options.ambiguity=='explicit', self.options.maybe_placeholders)
        callback = self._parse_tree_builder.create_callback(self.options.transformer)
        if self.profiler:
            for f in dir(callback):
                if not (f.startswith('__') and f.endswith('__')):
                    setattr(callback, f, self.profiler.make_wrapper('transformer', getattr(callback, f)))

        parser_conf = ParserConf(self.rules, callback, self.options.start)

        return self.parser_class(self.lexer_conf, parser_conf, options=self.options)

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

    def parse(self, text):
        "Parse the given text, according to the options provided. Returns a tree, unless specified otherwise."
        return self.parser.parse(text)

        # if self.profiler:
        #     self.profiler.enter_section('lex')
        #     l = list(self.lex(text))
        #     self.profiler.enter_section('parse')
        #     try:
        #         return self.parser.parse(l)
        #     finally:
        #         self.profiler.enter_section('outside_lark')
        # else:
        #     l = list(self.lex(text))
        #     return self.parser.parse(l)
