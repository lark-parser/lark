from __future__ import absolute_import

import os

from .utils import STRING_TYPE, inline_args
from .load_grammar import load_grammar
from .tree import Tree, Transformer

from .lexer import Lexer
from .grammar_analysis import GrammarAnalyzer, is_terminal
from . import parser, earley

class LarkOptions(object):
    """Specifies the options for Lark

    """
    OPTIONS_DOC = """
        parser - Which parser engine to use ("earley" or "lalr". Default: "earley")
                 Note: Both will use Lark's lexer.
        transformer - Applies the transformer to every parse tree
        debug - Affects verbosity (default: False)
        only_lex - Don't build a parser. Useful for debugging (default: False)
        keep_all_tokens - Don't automagically remove "punctuation" tokens (default: True)
        cache_grammar - Cache the Lark grammar (Default: False)
        postlex - Lexer post-processing (Default: None)
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

        assert self.parser in ENGINE_DICT
        if self.parser == 'earley' and self.transformer:
            raise ValueError('Cannot specify an auto-transformer when using the Earley algorithm. Please use your transformer on the resulting parse tree, or use a different algorithm (i.e. lalr)')
        if self.keep_all_tokens:
            raise NotImplementedError("Not implemented yet!")

        if o:
            raise ValueError("Unknown options: %s" % o.keys())


class Callback(object):
    pass


class RuleTreeToText(Transformer):
    def expansions(self, x):
        return x
    def expansion(self, symbols):
        return [sym.value for sym in symbols], None
    def alias(self, ((expansion, _alias), alias)):
        assert _alias is None, (alias, expansion, '-', _alias)
        return expansion, alias.value



def create_rule_handler(expansion, usermethod):
    to_include = [(i, sym.startswith('_')) for i, sym in enumerate(expansion)
                  if not (is_terminal(sym) and sym.startswith('_'))]

    def _build_ast(match):
        children = []
        for i, to_expand in to_include:
            if to_expand:
                children += match[i].children
            else:
                children.append(match[i])

        return usermethod(children)
    return _build_ast

def create_expand1_tree_builder_function(tree_builder):
    def f(children):
        if len(children) == 1:
            return children[0]
        else:
            return tree_builder(children)
    return f

class LALR:
    def build_parser(self, rules, callback):
        ga = GrammarAnalyzer(rules)
        ga.analyze()
        return parser.Parser(ga, callback)

class Earley:
    @staticmethod
    def _process_expansion(x):
        return [{'literal': s} if is_terminal(s) else s for s in x]

    def build_parser(self, rules, callback):
        rules = [{'name':n, 'symbols': self._process_expansion(x), 'postprocess':getattr(callback, a)} for n,x,a in rules]
        return EarleyParser(earley.Parser(rules, 'start'))

class EarleyParser:
    def __init__(self, parser):
        self.parser = parser

    def parse(self, text):
        res = self.parser.parse(text)
        assert len(res) ==1 , 'Ambiguious Parse! Not handled yet'
        return res[0]


ENGINE_DICT = { 'lalr': LALR, 'earley': Earley }

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

        self.tokens, self.rules = load_grammar(grammar)

        self.lexer = self._build_lexer()
        if not self.options.only_lex:
            self.parser_engine = ENGINE_DICT[self.options.parser]()
            self.parser = self._build_parser()

    def _build_lexer(self):
        ignore_tokens = []
        tokens = []
        for name, value, flags in self.tokens:
            if 'ignore' in flags:
                ignore_tokens.append(name)
            tokens.append((name, value))
        return Lexer(tokens, {}, ignore=ignore_tokens)


    def _build_parser(self):
        transformer = self.options.transformer
        callback = Callback()
        rules = []
        rule_tree_to_text = RuleTreeToText()
        for origin, tree in self.rules.items():
            for expansion, alias in rule_tree_to_text.transform(tree):
                if alias and origin.startswith('_'):
                    raise Exception("Rule %s is marked for expansion (it starts with an underscore) and isn't allowed to have aliases" % origin)

                expand1 = origin.startswith('?')
                _origin = origin.lstrip('?*')
                if alias:
                    alias = alias.lstrip('*')
                _alias = 'autoalias_%s_%s' % (_origin, '_'.join(expansion))

                try:
                    f = transformer._get_func(alias or _origin)
                    # f = getattr(transformer, alias or _origin)
                except AttributeError:
                    if alias:
                        f = self._create_tree_builder_function(alias)
                    else:
                        f = self._create_tree_builder_function(_origin)
                        if expand1:
                            f = create_expand1_tree_builder_function(f)

                alias_handler = create_rule_handler(expansion, f)

                assert not hasattr(callback, _alias)
                setattr(callback, _alias, alias_handler)

                rules.append((_origin, expansion, _alias))

        return self.parser_engine.build_parser(rules, callback)


    __init__.__doc__ += "\nOPTIONS:" + LarkOptions.OPTIONS_DOC

    def _create_tree_builder_function(self, name):
        tree_class = self.options.tree_class
        def f(children):
            return tree_class(name, children)
        return f

    def lex(self, text):
        stream = self.lexer.lex(text)
        if self.options.postlex:
            return self.options.postlex.process(stream)
        else:
            return stream

    def parse(self, text):
        assert not self.options.only_lex
        l = list(self.lex(text))
        return self.parser.parse(l)

