"My name is Earley"

from ..utils import classify
from ..common import ParseError, UnexpectedToken

try:
    xrange
except NameError:
    xrange = range

class MatchFailed(object):
    pass

class AbortParseMatch(Exception):
    pass


class Rule(object):
    def __init__(self, name, symbols, postprocess):
        self.name = name
        self.symbols = symbols
        self.postprocess = postprocess

class State(object):
    def __init__(self, rule, expect, reference, data=None):
        self.rule = rule
        self.expect = expect
        self.reference = reference
        self.data = data or []

        self.is_complete = (self.expect == len(self.rule.symbols))
        if not self.is_complete:
            self.expect_symbol = self.rule.symbols[self.expect]
            self.is_terminal = isinstance(self.expect_symbol, tuple)
        else:
            self.is_terminal = False

    def next_state(self, data):
        return State(self.rule, self.expect+1, self.reference, self.data + [data])

    def consume_terminal(self, inp):
        if not self.is_complete and self.is_terminal:
            # PORT: originally tests regexp

            if self.expect_symbol[1] is not None:
                match = self.expect_symbol[1].match(inp)
                if match:
                    return self.next_state(inp)

            elif self.expect_symbol[0] == inp.type:
                return self.next_state(inp)

    def consume_nonterminal(self, inp):
        if not self.is_complete and not self.is_terminal:

            if self.expect_symbol == inp:
                return self.next_state(inp)

    def process(self, location, ind, table, rules, added_rules):

        if self.is_complete:
            # Completed a rule
            if self.rule.postprocess:
                try:
                    self.data = self.rule.postprocess(self.data)
                except AbortParseMatch:
                    self.data = MatchFailed

            if self.data is not MatchFailed:
                for s in table[self.reference]:
                    x = s.consume_nonterminal(self.rule.name)
                    if x:
                        x.data[-1] = self.data
                        x.epsilon_closure(location, ind, table)

        else:
            exp = self.rule.symbols[self.expect]
            if isinstance(exp, tuple):
                return

            for r in rules[exp]:
                assert r.name == exp
                if r not in added_rules:
                    if r.symbols:
                        added_rules.add(r)
                        State(r, 0, location).epsilon_closure(location, ind, table)
                    else:
                        # Empty rule
                        new_copy = self.consume_nonterminal(r.name)
                        new_copy.data[-1] = r.postprocess([]) if r.postprocess else []

                        new_copy.epsilon_closure(location, ind, table)

    def epsilon_closure(self, location, ind, table):
        col = table[location]
        col.append(self)

        if not self.is_complete:
            for i in xrange(ind):
                state = col[i]
                if state.is_complete and state.reference == location:
                    x = self.consume_nonterminal(state.rule.name)
                    if x:
                        x.data[-1] = state.data
                        x.epsilon_closure(location, ind, table)


class Parser(object):
    def __init__(self, rules, start=None):
        self.rules = [Rule(r['name'], r['symbols'], r.get('postprocess', None)) for r in rules]
        self.rules_by_name = classify(self.rules, lambda r: r.name)
        self.start = start or self.rules[0].name

    def advance_to(self, table, added_rules):
        n = len(table)-1
        for w, s in enumerate(table[n]):
            s.process(n, w, table, self.rules_by_name, added_rules)

    def parse(self, stream):
        initial_rules = set(self.rules_by_name[self.start])
        table = [[State(r, 0, 0) for r in initial_rules]]
        self.advance_to(table, initial_rules)

        i = 0

        while i < len(stream):
            col = []

            token = stream[i]
            for s in table[-1]:
                x = s.consume_terminal(token)
                if x:
                    col.append(x)

            if not col:
                expected = {s.expect_symbol for s in table[-1] if s.is_terminal}
                raise UnexpectedToken(stream[i], expected, stream, i)

            table.append(col)
            self.advance_to(table, set())

            i += 1

        res = list(self.finish(table))
        if not res:
            raise ParseError('Incomplete parse')
        return res

    def finish(self, table):
        for t in table[-1]:
            if (t.rule.name == self.start
                and t.expect == len(t.rule.symbols)
                and t.reference == 0
                and t.data is not MatchFailed):
                yield t.data
