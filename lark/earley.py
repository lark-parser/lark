"My name is Earley"

from .utils import classify

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
            self.is_literal = isinstance(self.expect_symbol, dict)
            if self.is_literal:
                self.expect_symbol = self.expect_symbol['literal']
            assert isinstance(self.expect_symbol, (str, unicode)), self.expect_symbol

    def next_state(self, data):
        return State(self.rule, self.expect+1, self.reference, self.data + [data])

    def consume_terminal(self, inp):
        if not self.is_complete and self.is_literal:
            # PORT: originally tests regexp

            if self.expect_symbol == inp.type:
                return self.next_state(inp)

    def consume_nonterminal(self, inp):
        if not self.is_complete and not self.is_literal:

            if self.expect_symbol == inp:
                return self.next_state(inp)

    def process(self, location, ind, table, rules, added_rules):
        if self.is_complete:
            # Completed a rule
            if self.rule.postprocess:
                try:
                    # self.data = self.rule.postprocess(self.data, self.reference)
                    # import pdb
                    # pdb.set_trace()
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
            if isinstance(exp, dict):
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
                        if r.postprocess:
                            new_copy.data[-1] = r.postprocess([])
                            # new_copy.data[-1] = r.postprocess([], self.reference)
                        else:
                            new_copy.data[-1] = []

                        new_copy.epsilon_closure(location, ind, table)

    def epsilon_closure(self, location, ind, table, result=None):
        col = table[location]
        if not result:
            result = col

        result.append(self)

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
        self.table = [[]]
        self.rules = [Rule(r['name'], r['symbols'], r.get('postprocess', None)) for r in rules]
        self.rules_by_name = classify(self.rules, lambda r: r.name)
        self.start = start or self.rules[0].name
        initial_rules = set(self.rules_by_name[self.start])
        self.table[0] += [State(r, 0, 0) for r in initial_rules]
        self.advance_to(0, initial_rules)
        self.current = 0

    def advance_to(self, n, added_rules):
        for w, s in enumerate(self.table[n]):
            s.process(n, w, self.table, self.rules_by_name, added_rules)

    def parse(self, chunk):
        chunk_pos = 0
        for chunk_pos, chunk_item in enumerate(chunk):
            self.table.append([])

            for s in self.table[self.current + chunk_pos]:
                x = s.consume_terminal(chunk_item)
                if x:
                    self.table[self.current + chunk_pos + 1].append(x)


            added_rules = set()
            self.advance_to(self.current + chunk_pos + 1, added_rules)

            if not self.table[-1]:
                raise Exception('Error at line {t.line}:{t.column}'.format(t=chunk[chunk_pos]))

        self.current += chunk_pos
        return list(self.finish())

    def finish(self):
        for t in self.table[-1]:
            if (t.rule.name == self.start
                and t.expect == len(t.rule.symbols)
                and t.reference == 0
                and t.data != MatchFailed):
                yield t.data

