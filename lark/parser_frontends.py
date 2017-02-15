import re
import sre_parse

from .lexer import Lexer, ContextualLexer
from .parsers.lalr_analysis import GrammarAnalyzer

from .common import is_terminal, GrammarError
from .parsers import lalr_parser, earley

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

        analyzer = GrammarAnalyzer(parser_conf.rules, parser_conf.start)
        analyzer.analyze()
        self.parser = lalr_parser.Parser(analyzer, parser_conf.callback)

    def parse(self, text):
        tokens = list(self.lex(text))
        return self.parser.parse(tokens)

class LALR_ContextualLexer:
    def __init__(self, lexer_conf, parser_conf):
        self.lexer_conf = lexer_conf
        self.parser_conf = parser_conf

        self.analyzer = GrammarAnalyzer(parser_conf.rules, parser_conf.start)
        self.analyzer.analyze()

        d = {idx:t.keys() for idx, t in self.analyzer.states_idx.items()}
        self.lexer = ContextualLexer(lexer_conf.tokens, d, ignore=lexer_conf.ignore,
                                     always_accept=lexer_conf.postlex.always_accept
                                                   if lexer_conf.postlex else ())


    def parse(self, text):
        parser = lalr_parser.Parser(self.analyzer, self.parser_conf.callback)
        tokens = self.lexer.lex(text, parser)
        if self.lexer_conf.postlex:
            tokens = self.lexer_conf.postlex.process(tokens)
        return parser.parse(tokens, True)



class Earley(WithLexer):
    def __init__(self, lexer_conf, parser_conf):
        WithLexer.__init__(self, lexer_conf)

        rules = [{'name':n,
                  'symbols': list(self._prepare_expansion(x)),
                  'postprocess': getattr(parser_conf.callback, a)}
                  for n,x,a in parser_conf.rules]

        self.parser = earley.Parser(rules, parser_conf.start)

    def _prepare_expansion(self, expansion):
        for sym in expansion:
            if is_terminal(sym):
                yield sym, None
            else:
                yield sym

    def parse(self, text):
        tokens = list(self.lex(text))
        res = self.parser.parse(tokens)
        assert len(res) ==1 , 'Ambiguious Parse! Not handled yet'
        return res[0]

class Earley_NoLex:
    def __init__(self, lexer_conf, parser_conf):
        self.token_by_name = {t.name:t for t in lexer_conf.tokens}

        rules = [{'name':n,
                  'symbols': list(self._prepare_expansion(x)),
                  'postprocess': getattr(parser_conf.callback, a)}
                  for n,x,a in parser_conf.rules]

        self.parser = earley.Parser(rules, parser_conf.start)

    def _prepare_expansion(self, expansion):
        for sym in expansion:
            if is_terminal(sym):
                regexp = self.token_by_name[sym].to_regexp()
                width = sre_parse.parse(regexp).getwidth()
                if not width == (1,1):
                    raise GrammarError('Dynamic lexing requires all tokens have the width 1 (%s is %s)' % (regexp, width))
                yield sym, re.compile(regexp)
            else:
                yield sym

    def parse(self, text):
        res = self.parser.parse(text)
        assert len(res) ==1 , 'Ambiguious Parse! Not handled yet'
        return res[0]

ENGINE_DICT = { 'lalr': LALR, 'earley': Earley, 'earley_nolex': Earley_NoLex, 'lalr_contextual_lexer': LALR_ContextualLexer }
