from __future__ import absolute_import

import os
import time
from collections import defaultdict
from io import open

from .utils import STRING_TYPE, Serialize, SerializeMemoizer
from .load_grammar import load_grammar
from .tree import Tree
from .common import LexerConf, ParserConf

from .lexer import Lexer, TraditionalLexer
from .parse_tree_builder import ParseTreeBuilder
from .parser_frontends import get_frontend
from .grammar import Rule

###{standalone

class LarkOptions(Serialize):
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
        start - The start symbol, either a string, or a list of strings for multiple possible starts (Default: "start")
        profile - Measure run-time usage in Lark. Read results from the profiler proprety (Default: False)
        priority - How priorities should be evaluated - auto, none, normal, invert (Default: auto)
        propagate_positions - Propagates [line, column, end_line, end_column] attributes into all tree branches.
        lexer_callbacks - Dictionary of callbacks for the lexer. May alter tokens during lexing. Use with caution.
        maybe_placeholders - Experimental feature. Instead of omitting optional rules (i.e. rule?), replace them with None
    """
    if __doc__:
        __doc__ += OPTIONS_DOC

    _defaults = {
        'debug': False,
        'keep_all_tokens': False,
        'tree_class': None,
        'cache_grammar': False,
        'postlex': None,
        'parser': 'earley',
        'lexer': 'auto',
        'transformer': None,
        'start': 'start',
        'profile': False,
        'priority': 'auto',
        'ambiguity': 'auto',
        'propagate_positions': False,
        'lexer_callbacks': {},
        'maybe_placeholders': False,
        'edit_terminals': None,
    }

    def __init__(self, options_dict):
        o = dict(options_dict)

        options = {}
        for name, default in self._defaults.items():
            if name in o:
                value = o.pop(name)
                if isinstance(default, bool):
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
        return self.options[name]
    def __setattr__(self, name, value):
        assert name in self.options
        self.options[name] = value

    def serialize(self, memo):
        return self.options

    @classmethod
    def deserialize(cls, data, memo):
        return cls(data)


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


class Lark(Serialize):
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
        # self.profiler = Profiler() if self.options.profile else None

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
        self.terminals, self.rules, self.ignore_tokens = self.grammar.compile(self.options.start)

        if self.options.edit_terminals:
            for t in self.terminals:
                self.options.edit_terminals(t)

        self._terminals_dict = {t.name:t for t in self.terminals}

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

    if __init__.__doc__:
        __init__.__doc__ += "\nOPTIONS:" + LarkOptions.OPTIONS_DOC

    __serialize_fields__ = 'parser', 'rules', 'options'

    def _build_lexer(self):
        return TraditionalLexer(self.lexer_conf.tokens, ignore=self.lexer_conf.ignore, user_callbacks=self.lexer_conf.callbacks)

    def _prepare_callbacks(self):
        self.parser_class = get_frontend(self.options.parser, self.options.lexer)
        self._parse_tree_builder = ParseTreeBuilder(self.rules, self.options.tree_class or Tree, self.options.propagate_positions, self.options.keep_all_tokens, self.options.parser!='lalr' and self.options.ambiguity=='explicit', self.options.maybe_placeholders)
        self._callbacks = self._parse_tree_builder.create_callback(self.options.transformer)

    def _build_parser(self):
        self._prepare_callbacks()
        parser_conf = ParserConf(self.rules, self._callbacks, self.options.start)
        return self.parser_class(self.lexer_conf, parser_conf, options=self.options)

    @classmethod
    def deserialize(cls, data, namespace, memo, transformer=None, postlex=None):
        if memo:
            memo = SerializeMemoizer.deserialize(memo, namespace, {})
        inst = cls.__new__(cls)
        options = dict(data['options'])
        options['transformer'] = transformer
        options['postlex'] = postlex
        inst.options = LarkOptions.deserialize(options, memo)
        inst.rules = [Rule.deserialize(r, memo) for r in data['rules']]
        inst.source = '<deserialized>'
        inst._prepare_callbacks()
        inst.parser = inst.parser_class.deserialize(data['parser'], memo, inst._callbacks, inst.options.postlex)
        return inst


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

    def parse(self, text, start=None):
        """Parse the given text, according to the options provided.

        The 'start' parameter is required if Lark was given multiple possible start symbols (using the start option).

        Returns a tree, unless specified otherwise.
        """
        return self.parser.parse(text, start=start)

###}
