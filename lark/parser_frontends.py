from .parsers.lalr_analysis import GrammarAnalyzer

from .common import is_terminal
from .parsers import lalr_parser, earley

class LALR:
    def build_parser(self, rules, callback, start):
        ga = GrammarAnalyzer(rules, start)
        ga.analyze()
        return lalr_parser.Parser(ga, callback)

class Earley:
    @staticmethod
    def _process_expansion(x):
        return [{'literal': s} if is_terminal(s) else s for s in x]

    def build_parser(self, rules, callback, start):
        rules = [{'name':n, 'symbols': self._process_expansion(x), 'postprocess':getattr(callback, a)} for n,x,a in rules]
        return EarleyParser(earley.Parser(rules, start))

class EarleyParser:
    def __init__(self, parser):
        self.parser = parser

    def parse(self, text):
        res = self.parser.parse(text)
        assert len(res) ==1 , 'Ambiguious Parse! Not handled yet'
        return res[0]


ENGINE_DICT = { 'lalr': LALR, 'earley': Earley }

