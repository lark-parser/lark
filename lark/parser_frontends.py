import re
from .utils import get_regexp_width

from .lexer import Lexer, ContextualLexer, Token

from .common import is_terminal, GrammarError, ParserConf
from .parsers import lalr_parser, earley, xearley, resolve_ambig

class WithLexer:
    def init_traditional_lexer(self, lexer_conf):
        self.lexer_conf = lexer_conf
        self.lexer = Lexer(lexer_conf.tokens, ignore=lexer_conf.ignore)

    def init_contextual_lexer(self, lexer_conf, parser_conf):
        self.lexer_conf = lexer_conf
        d = {idx:t.keys() for idx, t in self.parser.analysis.parse_table.states.items()}
        always_accept = lexer_conf.postlex.always_accept if lexer_conf.postlex else ()
        self.lexer = ContextualLexer(lexer_conf.tokens, d, ignore=lexer_conf.ignore, always_accept=always_accept)

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

def get_ambiguity_resolver(options):
    if not options or options.ambiguity == 'resolve':
        return resolve_ambig.standard_resolve_ambig
    elif options.ambiguity == 'resolve__antiscore_sum':
        return resolve_ambig.antiscore_sum_resolve_ambig
    elif options.ambiguity == 'explicit':
        return None
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

        self.parser = earley.Parser(parser_conf, self.match,
                                    resolve_ambiguity=get_ambiguity_resolver(options))


    def match(self, term, text, index=0):
        return self.regexps[term].match(text, index)

    def _prepare_match(self, lexer_conf):
        self.regexps = {}
        for t in lexer_conf.tokens:
            regexp = t.pattern.to_regexp()
            width = get_regexp_width(regexp)
            if width != (1,1):
                raise GrammarError('Scanless parsing (lexer=None) requires all tokens to have a width of 1 (terminal %s: %s is %s)' % (sym, regexp, width))
            self.regexps[t.name] = re.compile(regexp)

    def parse(self, text):
        token_stream = tokenize_text(text)
        return self.parser.parse(token_stream)

class Earley(WithLexer):
    def __init__(self, lexer_conf, parser_conf, options=None):
        self.init_traditional_lexer(lexer_conf)

        self.parser = earley.Parser(parser_conf, self.match,
                                    resolve_ambiguity=get_ambiguity_resolver(options))

    def match(self, term, token):
        return term == token.type

    def parse(self, text):
        tokens = self.lex(text)
        return self.parser.parse(tokens)


class XEarley:
    def __init__(self, lexer_conf, parser_conf, options=None):
        self.token_by_name = {t.name:t for t in lexer_conf.tokens}

        self._prepare_match(lexer_conf)

        self.parser = xearley.Parser(parser_conf,
                                    self.match,
                                    resolve_ambiguity=get_ambiguity_resolver(options),
                                    ignore=lexer_conf.ignore,
                                    predict_all=options.earley__predict_all
                                    )

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



