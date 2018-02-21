import re
from .utils import get_regexp_width

from .parsers.grammar_analysis import GrammarAnalyzer
from .lexer import Lexer, ContextualLexer, Token

from .common import is_terminal, GrammarError
from .parsers import lalr_parser, earley, earley_forest, xearley, cyk
from .tree import Tree

class WithLexer:
    def init_traditional_lexer(self, lexer_conf):
        self.lexer_conf = lexer_conf
        self.lexer = Lexer(lexer_conf.tokens, ignore=lexer_conf.ignore, user_callbacks=lexer_conf.callbacks)

    def init_contextual_lexer(self, lexer_conf, parser_conf):
        self.lexer_conf = lexer_conf
        states = {idx:list(t.keys()) for idx, t in self.parser._parse_table.states.items()}
        always_accept = lexer_conf.postlex.always_accept if lexer_conf.postlex else ()
        self.lexer = ContextualLexer(lexer_conf.tokens, states, ignore=lexer_conf.ignore, always_accept=always_accept, user_callbacks=lexer_conf.callbacks)

    def lex(self, text):
        stream = self.lexer.lex(text)
        if self.lexer_conf.postlex:
            return self.lexer_conf.postlex.process(stream)
        else:
            return stream


class LALR(WithLexer):
    def __init__(self, lexer_conf, parser_conf, options=None):
        self.parser = lalr_parser.Parser(parser_conf)
        self.init_traditional_lexer(lexer_conf)

    def parse(self, text):
        token_stream = self.lex(text)
        return self.parser.parse(token_stream)


class LALR_ContextualLexer(WithLexer):
    def __init__(self, lexer_conf, parser_conf, options=None):
        self.parser = lalr_parser.Parser(parser_conf)
        self.init_contextual_lexer(lexer_conf, parser_conf)

    def parse(self, text):
        token_stream = self.lex(text)
        return self.parser.parse(token_stream, self.lexer.set_parser_state)

def get_ambiguity_options(options):
    if not options or options.ambiguity == 'resolve':
        return {}
    elif options.ambiguity == 'resolve__antiscore_sum':
        return {'forest_sum_visitor': earley_forest.ForestAntiscoreSumVisitor}
    elif options.ambiguity == 'explicit':
        return {'resolve_ambiguity': False}
    raise ValueError(options)

def tokenize_text(text):
    line = 1
    col_start_pos = 0
    for i, ch in enumerate(text):
        if '\n' in ch:
            line += ch.count('\n')
            col_start_pos = i + ch.rindex('\n')
        yield Token('CHAR', ch, line=line, column=i - col_start_pos)

class Earley_NoLex:
    def __init__(self, lexer_conf, parser_conf, options=None):
        self._prepare_match(lexer_conf)

        self.parser = earley.Parser(parser_conf, self.match, **get_ambiguity_options(options))


    def match(self, term, text, index=0):
        return self.regexps[term].match(text, index)

    def _prepare_match(self, lexer_conf):
        self.regexps = {}
        for t in lexer_conf.tokens:
            regexp = t.pattern.to_regexp()
            width = get_regexp_width(regexp)
            if width != (1,1):
                raise GrammarError('Scanless parsing (lexer=None) requires all tokens to have a width of 1 (terminal %s: %s is %s)' % (t.name, regexp, width))
            self.regexps[t.name] = re.compile(regexp)

    def parse(self, text):
        token_stream = tokenize_text(text)
        return self.parser.parse(token_stream)

class Earley(WithLexer):
    def __init__(self, lexer_conf, parser_conf, options=None):
        self.init_traditional_lexer(lexer_conf)

        self.parser = earley.Parser(parser_conf, self.match, **get_ambiguity_options(options))

    def match(self, term, token):
        return term == token.type

    def parse(self, text):
        tokens = self.lex(text)
        return self.parser.parse(tokens)


class XEarley:
    def __init__(self, lexer_conf, parser_conf, options=None):
        self.token_by_name = {t.name:t for t in lexer_conf.tokens}

        self._prepare_match(lexer_conf)

        self.parser = xearley.Parser(parser_conf, self.match, ignore=lexer_conf.ignore, **get_ambiguity_options(options))

    def match(self, term, text, index=0):
        return self.regexps[term].match(text, index)

    def _prepare_match(self, lexer_conf):
        self.regexps = {}
        for t in lexer_conf.tokens:
            regexp = t.pattern.to_regexp()
            try:
                width = get_regexp_width(regexp)[0]
            except ValueError:
                raise ValueError("Bad regexp in token %s: %s" % (t.name, regexp))
            else:
                if width == 0:
                    raise ValueError("Dynamic Earley doesn't allow zero-width regexps", t)

            self.regexps[t.name] = re.compile(regexp)

    def parse(self, text):
        return self.parser.parse(text)


class CYK(WithLexer):

    def __init__(self, lexer_conf, parser_conf, options=None):
        self.init_traditional_lexer(lexer_conf)

        self._analysis = GrammarAnalyzer(parser_conf)
        self._parser = cyk.Parser(parser_conf.rules, parser_conf.start)

        self._postprocess = {}
        for rule in parser_conf.rules:
            a = rule.alias
            self._postprocess[a] = a if callable(a) else (a and getattr(parser_conf.callback, a))

    def parse(self, text):
        tokens = list(self.lex(text))
        parse = self._parser.parse(tokens)
        parse = self._transform(parse)
        return parse

    def _transform(self, tree):
        subtrees = list(tree.iter_subtrees())
        for subtree in subtrees:
            subtree.children = [self._apply_callback(c) if isinstance(c, Tree) else c for c in subtree.children]

        return self._apply_callback(tree)

    def _apply_callback(self, tree):
        children = tree.children
        callback = self._postprocess[tree.rule.alias]
        assert callback, tree.rule.alias
        r = callback(children)
        return r


def get_frontend(parser, lexer):
    if parser=='lalr':
        if lexer is None:
            raise ValueError('The LALR parser requires use of a lexer')
        elif lexer == 'standard':
            return LALR
        elif lexer == 'contextual':
            return LALR_ContextualLexer
        else:
            raise ValueError('Unknown lexer: %s' % lexer)
    elif parser=='earley':
        if lexer is None:
            return Earley_NoLex
        elif lexer=='standard':
            return Earley
        elif lexer=='dynamic':
            return XEarley
        elif lexer=='contextual':
            raise ValueError('The Earley parser does not support the contextual parser')
        else:
            raise ValueError('Unknown lexer: %s' % lexer)
    elif parser == 'cyk':
        if lexer == 'standard':
            return CYK
        else:
            raise ValueError('CYK parser requires using standard parser.')
    else:
        raise ValueError('Unknown parser: %s' % parser)



