from __future__ import absolute_import

import os
import time
from collections import defaultdict

from .utils import STRING_TYPE
from .load_grammar import load_grammar
from .tree import Tree
from .common import GrammarError, LexerConf, ParserConf

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
            raise ValueError('Cannot specify an auto-transformer when using the Earley algorithm.'
                             'Please use your transformer on the resulting parse tree, or use a different algorithm (i.e. lalr)')
        if self.keep_all_tokens:
            raise NotImplementedError("Not implemented yet!")

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

        if self.options.cache_grammar or self.options.keep_all_tokens:
            raise NotImplementedError("Not available yet")

        assert not self.options.profile, "Feature temporarily disabled"
        self.profiler = Profiler() if self.options.profile else None

        tokens, self.rules = load_grammar(grammar)
        self.ignore_tokens = []
        for tokendef, flags in tokens:
            for flag in flags:
                if flag == 'ignore':
                    self.ignore_tokens.append(tokendef.name)
                else:
                    raise GrammarError("No such flag: %s" % flag)

        self.lexer_conf = LexerConf([t[0] for t in tokens], self.ignore_tokens, self.options.postlex)

        if not self.options.only_lex:
            self.parser = self._build_parser()
        else:
            self.lexer = self._build_lexer()

        if self.profiler: self.profiler.enter_section('outside_lark')

    __init__.__doc__ += "\nOPTIONS:" + LarkOptions.OPTIONS_DOC

    def _build_lexer(self):
        return Lexer(self.lexer_conf.tokens, ignore=self.lexer_conf.ignore)

    def _build_parser(self):
        self.parser_class = ENGINE_DICT[self.options.parser]
        self.parse_tree_builder = ParseTreeBuilder(self.options.tree_class)
        rules, callback = self.parse_tree_builder.create_tree_builder(self.rules, self.options.transformer)
        if self.profiler:
            for f in dir(callback):
                if not (f.startswith('__') and f.endswith('__')):
                    setattr(callback, f, self.profiler.make_wrapper('transformer', getattr(callback, f)))
        parser_conf = ParserConf(rules, callback, self.options.start)

        return self.parser_class(self.lexer_conf, parser_conf)


    def lex(self, text):
        stream = self.lexer.lex(text)
        if self.options.postlex:
            return self.options.postlex.process(stream)
        else:
            return stream

    def parse(self, text):
        assert not self.options.only_lex

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

