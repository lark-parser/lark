import re
import sre_parse

from .lexer import Lexer, ContextualLexer, Token

from .common import is_terminal, GrammarError, ParserConf
from .parsers import lalr_parser, earley, nearley
from .parsers.grammar_analysis import Rule
from .tree import Transformer

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
    def __init__(self, lexer_conf, parser_conf):
        WithLexer.__init__(self, lexer_conf)

        self.parser_conf = parser_conf
        self.parser = lalr_parser.Parser(parser_conf)

    def parse(self, text):
        tokens = list(self.lex(text))
        return self.parser.parse(tokens)

class LALR_ContextualLexer:
    def __init__(self, lexer_conf, parser_conf):
        self.lexer_conf = lexer_conf
        self.parser_conf = parser_conf

        self.parser = lalr_parser.Parser(parser_conf)

        d = {idx:t.keys() for idx, t in self.parser.analysis.states_idx.items()}
        self.lexer = ContextualLexer(lexer_conf.tokens, d, ignore=lexer_conf.ignore,
                                     always_accept=lexer_conf.postlex.always_accept
                                                   if lexer_conf.postlex else ())


    def parse(self, text):
        tokens = self.lexer.lex(text)
        if self.lexer_conf.postlex:
            tokens = self.lexer_conf.postlex.process(tokens)
        return self.parser.parse(tokens, self.lexer.set_parser_state)



class Nearley(WithLexer):
    def __init__(self, lexer_conf, parser_conf):
        WithLexer.__init__(self, lexer_conf)

        rules = [{'name':n,
                  'symbols': self._prepare_expansion(x),
                  'postprocess': getattr(parser_conf.callback, a)}
                  for n,x,a in parser_conf.rules]

        self.parser = nearley.Parser(rules, parser_conf.start)

    def _prepare_expansion(self, expansion):
        return [(sym, None) if is_terminal(sym) else sym for sym in expansion]

    def parse(self, text):
        tokens = list(self.lex(text))
        res = self.parser.parse(tokens)
        assert len(res) ==1 , 'Ambiguious Parse! Not handled yet'
        return res[0]


class Earley(WithLexer):
    def __init__(self, lexer_conf, parser_conf):
        WithLexer.__init__(self, lexer_conf)

        rules = [(n, self._prepare_expansion(x), a)
                 for n,x,a in parser_conf.rules]

        self.parser = earley.Parser(ParserConf(rules, parser_conf.callback, parser_conf.start))

    def _prepare_expansion(self, expansion):
        return [(sym,) if is_terminal(sym) else sym for sym in expansion]

    def parse(self, text):
        tokens = list(self.lex(text))
        res = self.parser.parse(tokens)
        assert len(res) ==1 , 'Ambiguious Parse! Not handled yet'
        return res[0]


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

class Nearley_NoLex:
    def __init__(self, lexer_conf, parser_conf):
        self.tokens_to_convert = {name: '__token_'+name for name, tree, _ in parser_conf.rules if is_terminal(name)}
        rules = []
        for name, exp, alias in parser_conf.rules:
            name = self.tokens_to_convert.get(name, name)
            exp = [self.tokens_to_convert.get(x, x) for x in exp]
            rules.append((name, exp, alias))

        self.token_by_name = {t.name:t for t in lexer_conf.tokens}

        rules = [{'name':n,
                  'symbols': list(self._prepare_expansion(x)),
                  'postprocess': getattr(parser_conf.callback, a)}
                  for n,x,a in rules]

        self.parser = nearley.Parser(rules, parser_conf.start)

    def _prepare_expansion(self, expansion):
        for sym in expansion:
            if is_terminal(sym):
                regexp = self.token_by_name[sym].pattern.to_regexp()
                width = sre_parse.parse(regexp).getwidth()
                if not width == (1,1):
                    raise GrammarError('Dynamic lexing requires all tokens to have a width of 1 (%s is %s)' % (regexp, width))
                yield sym, re.compile(regexp)
            else:
                yield sym

    def parse(self, text):
        new_text = tokenize_text(text)
        res = self.parser.parse(new_text)
        assert len(res) ==1 , 'Ambiguious Parse! Not handled yet'
        res = res[0]

        class RestoreTokens(Transformer):
            pass

        for t in self.tokens_to_convert:
            setattr(RestoreTokens, t, ''.join)

        res = RestoreTokens().transform(res)
        return res


class Earley_NoLex:
    def __init__(self, lexer_conf, parser_conf):
        self.tokens_to_convert = {name: '__token_'+name for name, tree, _ in parser_conf.rules if is_terminal(name)}
        rules = []
        for name, exp, alias in parser_conf.rules:
            name = self.tokens_to_convert.get(name, name)
            exp = [self.tokens_to_convert.get(x, x) for x in exp]
            rules.append((name, exp, alias))

        self.token_by_name = {t.name:t for t in lexer_conf.tokens}

        rules = [(n, list(self._prepare_expansion(x)), a) for n,x,a in rules]

        self.parser = earley.Parser(ParserConf(rules, parser_conf.callback, parser_conf.start))

    def _prepare_expansion(self, expansion):
        for sym in expansion:
            if is_terminal(sym):
                regexp = self.token_by_name[sym].pattern.to_regexp()
                width = sre_parse.parse(regexp).getwidth()
                if not width == (1,1):
                    raise GrammarError('Scanless parsing (lexer=None) requires all tokens to have a width of 1 (terminal %s: %s is %s)' % (sym, regexp, width))
                yield (re.compile(regexp).match, regexp)
            else:
                yield sym

    def parse(self, text):
        new_text = tokenize_text(text)
        res = self.parser.parse(new_text)
        assert len(res) ==1 , 'Ambiguious Parse! Not handled yet'
        res = res[0]

        class RestoreTokens(Transformer):
            pass

        for t in self.tokens_to_convert:
            setattr(RestoreTokens, t, ''.join)

        res = RestoreTokens().transform(res)
        return res


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
        elif lexer=='contextual':
            raise ValueError('The Earley parser does not support the contextual parser')
        else:
            raise ValueError('Unknown lexer: %s' % lexer)
    else:
        raise ValueError('Unknown parser: %s' % parser)



