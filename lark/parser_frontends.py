from .lexer import Lexer
from .parsers.lalr_analysis import GrammarAnalyzer

from .common import is_terminal
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

class Earley(WithLexer):
    def __init__(self, lexer_conf, parser_conf):
        WithLexer.__init__(self, lexer_conf)

        rules = [{'name':n,
                  'symbols': self._process_expansion(x),
                  'postprocess': getattr(parser_conf.callback, a)}
                  for n,x,a in parser_conf.rules]

        self.parser = earley.Parser(rules, parser_conf.start)

    def parse(self, text):
        tokens = list(self.lex(text))
        res = self.parser.parse(tokens)
        assert len(res) ==1 , 'Ambiguious Parse! Not handled yet'
        return res[0]

    @staticmethod
    def _process_expansion(x):
        return [{'literal': s} if is_terminal(s) else s for s in x]



ENGINE_DICT = { 'lalr': LALR, 'earley': Earley }

