import re
from collections import defaultdict

from .tree import Tree
from .common import is_terminal
from .lexer import Token, TokenDef__Str
from .parsers import earley
from .lark import Lark



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
        tokens = {t.name:t for t in parser.lexer_conf.tokens}
        token_res = {t.name:re.compile(t.to_regexp()) for t in parser.lexer_conf.tokens}

        class MatchData:
            def __init__(self, data):
                self.data = data

        class MatchTerminal(MatchData):
            def match(self, other):
                return token_res[self.data].match(other) is not None

        class MatchTree(MatchData):
            def match(self, other):
                return self.data == other.data

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
                        assert isinstance(t, TokenDef__Str)
                        to_write.append(t.value)
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
        for name, expansions in parser.rules.items():
            for expansion, alias in expansions:
                if alias:
                    d[alias].append(expansion)
                    d[name].append([alias])
                else:
                    d[name].append(expansion)

        rules = []
        expand1s = {name.lstrip('!').lstrip('?') for name in d
                    if name.startswith(('?', '!?'))}    # XXX Ugly code

        for name, expansions in d.items():
            for expansion in expansions:
                reduced = [sym if sym.startswith('_') or sym in expand1s else
                           (sym, MatchTerminal(sym) if is_terminal(sym) else MatchTree(sym))
                           for sym in expansion if not is_discarded_terminal(sym)]

                name = name.lstrip('!').lstrip('?')

                rules.append({'name': name,
                              'symbols': reduced,
                              'postprocess': WriteTokens(name, expansion).f
                              })
        self.rules = rules


    def _reconstruct(self, tree):
        parser = earley.Parser(self.rules, tree.data)

        res ,= parser.parse(tree.children)  # XXX ambiguity?
        for item in res:
            if isinstance(item, Tree):
                for x in self._reconstruct(item):
                    yield x
            else:
                yield item

    def reconstruct(self, tree):
        return ''.join(self._reconstruct(tree))


