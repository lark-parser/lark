from collections import defaultdict

from .tree import Tree
from .common import is_terminal, ParserConf, PatternStr
from .lexer import Token
from .parsers import earley
from .grammar import Rule



def is_discarded_terminal(t):
    return is_terminal(t) and t.startswith('_')

def is_iter_empty(i):
    try:
        _ = next(i)
        return False
    except StopIteration:
        return True

class Reconstructor:
    def __init__(self, parser):
        # Recreate the rules to assume a standard lexer
        _tokens, rules, _grammar_extra = parser.grammar.compile(lexer='standard', start='whatever')
        tokens = {t.name:t for t in _tokens}


        class WriteTokens:
            def __init__(self, name, expansion):
                self.name = name
                self.expansion = expansion

            def f(self, args):
                iter_args = iter(args)
                to_write = []
                for sym in self.expansion:
                    if is_discarded_terminal(sym):
                        t = tokens[sym]
                        assert isinstance(t.pattern, PatternStr)
                        to_write.append(t.pattern.value)
                    else:
                        x = next(iter_args)
                        if isinstance(x, list):
                            to_write += x
                        else:
                            if isinstance(x, Token):
                                assert x.type == sym, x
                            else:
                                assert x.data == sym, x
                            to_write.append(x)

                assert is_iter_empty(iter_args)
                return to_write

        expand1s = {r.origin for r in parser.rules if r.options and r.options.expand1}

        d = defaultdict(list)
        for r in rules:
            if r.alias:
                d[r.alias].append(r.expansion)
                d[r.origin].append([r.alias])
            else:
                d[r.origin].append(r.expansion)

        self.rules = []
        for name, expansions in d.items():
            for expansion in expansions:
                reduced = [sym if sym.startswith('_') or sym in expand1s else sym.upper()
                           for sym in expansion if not is_discarded_terminal(sym)]

                self.rules.append(Rule(name, reduced, WriteTokens(name, expansion).f, None))


    def _match(self, term, token):
        if isinstance(token, Tree):
            return token.data.upper() == term
        elif isinstance(token, Token):
            return term == token.type
        assert False

    def _reconstruct(self, tree):
        # TODO: ambiguity?
        parser = earley.Parser(ParserConf(self.rules, None, tree.data), self._match)
        res = parser.parse(tree.children)
        for item in res:
            if isinstance(item, Tree):
                for x in self._reconstruct(item):
                    yield x
            else:
                yield item

    def reconstruct(self, tree):
        return ''.join(self._reconstruct(tree))

