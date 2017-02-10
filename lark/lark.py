from __future__ import absolute_import

import os

from .utils import STRING_TYPE, inline_args
from .load_grammar import load_grammar
from .tree import Tree, Transformer
from .common import GrammarError

from .lexer import Lexer
from .parse_tree_builder import ParseTreeBuilder
from .parser_frontends import ENGINE_DICT

class LarkOptions(object):
    """Specifies the options for Lark

    """
    OPTIONS_DOC = """
        parser - Which parser engine to use ("earley" or "lalr". Default: "earley")
                 Note: Both will use Lark's lexer.
        transformer - Applies the transformer to every parse tree
        debug - Affects verbosity (default: False)
        only_lex - Don't build a parser. Useful for debugging (default: False)
        keep_all_tokens - Don't automagically remove "punctuation" tokens (default: False)
        cache_grammar - Cache the Lark grammar (Default: False)
        postlex - Lexer post-processing (Default: None)
        start - The start symbol (Default: start)
        profile - Measure run-time usage in Lark. Read results from the profiler proprety (Default: False)
    """
    __doc__ += OPTIONS_DOC
    def __init__(self, options_dict):
        o = dict(options_dict)

        self.debug = bool(o.pop('debug', False))
        self.only_lex = bool(o.pop('only_lex', False))
        self.keep_all_tokens = bool(o.pop('keep_all_tokens', False))
        self.tree_class = o.pop('tree_class', Tree)
        self.cache_grammar = o.pop('cache_grammar', False)
        self.postlex = o.pop('postlex', None)
        self.parser = o.pop('parser', 'earley')
        self.transformer = o.pop('transformer', None)
        self.start = o.pop('start', 'start')
        self.profile = o.pop('profile', False)

        assert self.parser in ENGINE_DICT
        if self.parser == 'earley' and self.transformer:
            raise ValueError('Cannot specify an auto-transformer when using the Earley algorithm. Please use your transformer on the resulting parse tree, or use a different algorithm (i.e. lalr)')
        if self.keep_all_tokens:
            raise NotImplementedError("Not implemented yet!")

        if o:
            raise ValueError("Unknown options: %s" % o.keys())


import time
from collections import defaultdict
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
        def _f(*args, **kwargs):
            last_section = self.cur_section
            self.enter_section(name)
            try:
                return f(*args, **kwargs)
            finally:
                self.enter_section(last_section)

        return _f


class Lark:
    def __init__(self, grammar, **options):
        """
            grammar : a string or file-object containing the grammar spec (using Lark's ebnf syntax)
            options : a dictionary controlling various aspects of Lark.
        """
        self.options = LarkOptions(options)

        # Some, but not all file-like objects have a 'name' attribute
        try:
            source = grammar.name
        except AttributeError:
            source = '<string>'
            cache_file = "larkcache_%s" % str(hash(grammar)%(2**32))
        else:
            cache_file = "larkcache_%s" % os.path.basename(source)

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

        self.profiler = Profiler() if self.options.profile else None

        self.tokens, self.rules = load_grammar(grammar)

        self.lexer = self._build_lexer()
        if not self.options.only_lex:
            self.parser_engine = ENGINE_DICT[self.options.parser]()
            self.parse_tree_builder = ParseTreeBuilder(self.options.tree_class)
            self.parser = self._build_parser()

        if self.profiler: self.profiler.enter_section('outside_lark')


    def _create_unless_callback(self, strs):
        def f(t):
            if t in strs:
                t.type = strs[t]
            return t
        return f

    def _build_lexer(self):
        ignore_tokens = []
        tokens = []
        callbacks = {}
        for name, value, flags in self.tokens:
            for flag in flags:
                if flag == 'ignore':
                    ignore_tokens.append(name)
                elif isinstance(flag, tuple) and flag[0] == 'unless':
                    _, strs = flag
                    callbacks[name] = self._create_unless_callback(strs)
                else:
                    raise GrammarError("No such flag: %s" % flag)

            tokens.append((name, value))
        return Lexer(tokens, callbacks, ignore=ignore_tokens)


    def _build_parser(self):
        rules, callback = self.parse_tree_builder.create_tree_builder(self.rules, self.options.transformer)
        if self.profiler:
            for f in dir(callback):
                if not f.startswith('__'):
                    setattr(callback, f, self.profiler.make_wrapper('transformer', getattr(callback, f)))
        return self.parser_engine.build_parser(rules, callback, self.options.start)


    __init__.__doc__ += "\nOPTIONS:" + LarkOptions.OPTIONS_DOC

    def lex(self, text):
        stream = self.lexer.lex(text)
        if self.options.postlex:
            return self.options.postlex.process(stream)
        else:
            return stream

    def parse(self, text):
        assert not self.options.only_lex

        if self.profiler:
            self.profiler.enter_section('lex')
            l = list(self.lex(text))
            self.profiler.enter_section('parse')
            try:
                return self.parser.parse(l)
            finally:
                self.profiler.enter_section('outside_lark')
        else:
            l = list(self.lex(text))
            return self.parser.parse(l)

