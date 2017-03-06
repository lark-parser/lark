import re
from collections import defaultdict

from .tree import Tree
from .common import is_terminal, ParserConf, PatternStr, Terminal
from .lexer import Token
from .parsers import earley



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

        token_res = {t.name:re.compile(t.pattern.to_regexp()) for t in _tokens}

        class MatchTerminal(Terminal):
            def match(self, other):
                if isinstance(other, Tree):
                    return False
                return token_res[self.data].match(other) is not None

        class MatchTree(Terminal):
            def match(self, other):
                try:
                    return self.data == other.data
                except AttributeError:
                    return False

        class WriteTokens:
            def __init__(self, name, expansion):
                self.name = name
                self.expansion = expansion

            def f(self, args):
                args2 = iter(args)
                to_write = []
                for sym in self.expansion:
                    if is_discarded_terminal(sym):
                        t = tokens[sym]
                        assert isinstance(t.pattern, PatternStr)
                        to_write.append(t.pattern.value)
                    else:
                        x = next(args2)
                        if isinstance(x, list):
                            to_write += x
                        else:
                            if isinstance(x, Token):
                                assert x.type == sym, x
                            else:
                                assert x.data == sym, x
                            to_write.append(x)

                assert is_iter_empty(args2)

                return to_write

        d = defaultdict(list)
        for name, (expansions, _o) in rules.items():
            for expansion, alias in expansions:
                if alias:
                    d[alias].append(expansion)
                    d[name].append([alias])
                else:
                    d[name].append(expansion)

        rules = []
        expand1s = {name for name, (_x, options) in parser.rules.items()
                    if options and options.expand1}

        for name, expansions in d.items():
            for expansion in expansions:
                reduced = [sym if sym.startswith('_') or sym in expand1s else
                           MatchTerminal(sym) if is_terminal(sym) else MatchTree(sym)
                           for sym in expansion if not is_discarded_terminal(sym)]

                rules.append((name, reduced, WriteTokens(name, expansion).f))
        self.rules = rules


    def _reconstruct(self, tree):
        # TODO: ambiguity?
        parser = earley.Parser(self.rules, tree.data, {})
        res = parser.parse(tree.children)
        for item in res:
            if isinstance(item, Tree):
                for x in self._reconstruct(item):
                    yield x
            else:
                yield item

    def reconstruct(self, tree):
        return ''.join(self._reconstruct(tree))

