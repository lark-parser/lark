import re
import sre_parse

from parsers.grammar_analysis import GrammarAnalyzer
from .lexer import Lexer, ContextualLexer, Token

from .common import is_terminal, GrammarError, Terminal_Regexp, Terminal_Token
from .parsers import lalr_parser, earley, xearley, resolve_ambig, cyk
from .tree import Tree

class WithLexer:
    def __init__(self, lexer_conf):
        self.lexer_conf = lexer_conf
        self.lexer = Lexer(lexer_conf.tokens, ignore=lexer_conf.ignore)

    def lex(self, text):
        stream = self.lexer.lex(text)
        if self.lexer_conf.postlex:
            return self.lexer_conf.postlex.process(stream)
        else:
            return stream


class LALR(WithLexer):
    def __init__(self, lexer_conf, parser_conf, options=None):
        WithLexer.__init__(self, lexer_conf)

        self.parser_conf = parser_conf
        self.parser = lalr_parser.Parser(parser_conf)

    def parse(self, text):
        tokens = self.lex(text)
        return self.parser.parse(tokens)


class LALR_ContextualLexer:
    def __init__(self, lexer_conf, parser_conf, options=None):
        self.lexer_conf = lexer_conf
        self.parser_conf = parser_conf

        self.parser = lalr_parser.Parser(parser_conf)

        d = {idx:t.keys() for idx, t in self.parser.analysis.states_idx.items()}
        always_accept = lexer_conf.postlex.always_accept if lexer_conf.postlex else ()
        self.lexer = ContextualLexer(lexer_conf.tokens, d, ignore=lexer_conf.ignore, always_accept=always_accept)

    def parse(self, text):
        tokens = self.lexer.lex(text)
        if self.lexer_conf.postlex:
            tokens = self.lexer_conf.postlex.process(tokens)
        return self.parser.parse(tokens, self.lexer.set_parser_state)

def get_ambiguity_resolver(options):
    if not options or options.ambiguity == 'resolve':
        return resolve_ambig.standard_resolve_ambig
    elif options.ambiguity == 'resolve__antiscore_sum':
        return resolve_ambig.antiscore_sum_resolve_ambig
    elif options.ambiguity == 'explicit':
        return None
    raise ValueError(options)

def tokenize_text(text):
    new_text = []
    line = 1
    col_start_pos = 0
    for i, ch in enumerate(text):
        if '\n' in ch:
            line += ch.count('\n')
            col_start_pos = i + ch.rindex('\n')
        new_text.append(Token('CHAR', ch, line=line, column=i - col_start_pos))
    return new_text

class Earley_NoLex:
    def __init__(self, lexer_conf, parser_conf, options=None):
        self.token_by_name = {t.name:t for t in lexer_conf.tokens}

        rules = [(n, list(self._prepare_expansion(x)), a, o) for n,x,a,o in parser_conf.rules]

        self.parser = earley.Parser(rules,
                                    parser_conf.start,
                                    parser_conf.callback,
                                    resolve_ambiguity=get_ambiguity_resolver(options))

    def _prepare_expansion(self, expansion):
        for sym in expansion:
            if is_terminal(sym):
                regexp = self.token_by_name[sym].pattern.to_regexp()
                width = sre_parse.parse(regexp).getwidth()
                if width != (1,1):
                    raise GrammarError('Scanless parsing (lexer=None) requires all tokens to have a width of 1 (terminal %s: %s is %s)' % (sym, regexp, width))
                yield Terminal_Regexp(sym, regexp)
            else:
                yield sym

    def parse(self, text):
        new_text = tokenize_text(text)
        return self.parser.parse(new_text)

class Earley(WithLexer):
    def __init__(self, lexer_conf, parser_conf, options=None):
        WithLexer.__init__(self, lexer_conf)

        rules = [(n, self._prepare_expansion(x), a, o) for n,x,a,o in parser_conf.rules]

        self.parser = earley.Parser(rules,
                                    parser_conf.start,
                                    parser_conf.callback,
                                    resolve_ambiguity=get_ambiguity_resolver(options))

    def _prepare_expansion(self, expansion):
        return [Terminal_Token(sym) if is_terminal(sym) else sym for sym in expansion]

    def parse(self, text):
        tokens = self.lex(text)
        return self.parser.parse(tokens)


class XEarley:
    def __init__(self, lexer_conf, parser_conf, options=None):
        self.token_by_name = {t.name:t for t in lexer_conf.tokens}

        rules = [(n, list(self._prepare_expansion(x)), a, o) for n,x,a,o in parser_conf.rules]

        ignore = [Terminal_Regexp(x, self.token_by_name[x].pattern.to_regexp()) for x in lexer_conf.ignore]

        self.parser = xearley.Parser(rules,
                                    parser_conf.start,
                                    parser_conf.callback,
                                    resolve_ambiguity=get_ambiguity_resolver(options),
                                    ignore=ignore,
                                    predict_all=options.earley__predict_all
                                    )

    def _prepare_expansion(self, expansion):
        for sym in expansion:
            if is_terminal(sym):
                regexp = self.token_by_name[sym].pattern.to_regexp()
                width = sre_parse.parse(regexp).getwidth()
                assert width
                yield Terminal_Regexp(sym, regexp)
            else:
                yield sym

    def parse(self, text):
        return self.parser.parse(text)


class CYK(WithLexer):

  def __init__(self, lexer_conf, parser_conf, options=None):
    WithLexer.__init__(self, lexer_conf)
    # TokenDef from synthetic rule to terminal value
    self._token_by_name = {t.name: t for t in lexer_conf.tokens}
    rules = [(lhs, self._prepare_expansion(rhs), cb, opt) for lhs, rhs, cb, opt in parser_conf.rules]
    self._analysis = GrammarAnalyzer(rules, parser_conf.start)
    self._parser = cyk.Parser(self._analysis.rules, parser_conf.start)

    self._postprocess = {}
    for rule in self._analysis.rules:
        if rule.origin != '$root':  # XXX kinda ugly
            a = rule.alias
            self._postprocess[a] = a if callable(a) else (a and getattr(parser_conf.callback, a))

  def _prepare_expansion(self, expansion):
    return [
        Terminal_Regexp(sym, self._token_by_name[sym].pattern.to_regexp())
        if is_terminal(sym) else sym for sym in expansion
    ]

  def parse(self, text):
    tokenized = [token.value for token in self.lex(text)]
    parse = self._parser.parse(tokenized)
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



