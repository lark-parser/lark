import re
import sre_parse

from .lexer import Lexer, ContextualLexer, Token

from .common import is_terminal, GrammarError, ParserConf, Terminal_Regexp, Terminal_Token
from .parsers import lalr_parser, earley, xearley

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

        resolve_ambiguity = (options.ambiguity=='resolve') if options else True
        self.parser = earley.Parser(rules, 
                                    parser_conf.start,
                                    parser_conf.callback,
                                    resolve_ambiguity=resolve_ambiguity)

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

        resolve_ambiguity = (options.ambiguity=='resolve') if options else True
        self.parser = earley.Parser(rules, 
                                    parser_conf.start,
                                    parser_conf.callback,
                                    resolve_ambiguity=resolve_ambiguity)

    def _prepare_expansion(self, expansion):
        return [Terminal_Token(sym) if is_terminal(sym) else sym for sym in expansion]

    def parse(self, text):
        tokens = self.lex(text)
        return self.parser.parse(tokens)


class XEarley:
    def __init__(self, lexer_conf, parser_conf, options=None):
        self.token_by_name = {t.name:t for t in lexer_conf.tokens}

        rules = [(n, list(self._prepare_expansion(x)), a, o) for n,x,a,o in parser_conf.rules]

        resolve_ambiguity = (options.ambiguity=='resolve') if options else True
        ignore = [Terminal_Regexp(x, self.token_by_name[x].pattern.to_regexp()) for x in lexer_conf.ignore]

        self.parser = xearley.Parser(rules,
                                    parser_conf.start,
                                    parser_conf.callback,
                                    resolve_ambiguity=resolve_ambiguity,
                                    ignore=ignore,
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
    else:
        raise ValueError('Unknown parser: %s' % parser)



