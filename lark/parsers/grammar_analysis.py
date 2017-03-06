
from ..utils import bfs, fzset
from ..common import GrammarError, is_terminal

class Rule(object):
    """
        origin : a symbol
        expansion : a list of symbols
    """
    def __init__(self, origin, expansion, alias=None):
        self.origin = origin
        self.expansion = expansion
        self.alias = alias

    def __repr__(self):
        return '<%s : %s>' % (self.origin, ' '.join(map(str,self.expansion)))

class RulePtr(object):
    def __init__(self, rule, index):
        assert isinstance(rule, Rule)
        assert index <= len(rule.expansion)
        self.rule = rule
        self.index = index

    def __repr__(self):
        before = self.rule.expansion[:self.index]
        after = self.rule.expansion[self.index:]
        return '<%s : %s * %s>' % (self.rule.origin, ' '.join(before), ' '.join(after))

    @property
    def next(self):
        return self.rule.expansion[self.index]

    def advance(self, sym):
        assert self.next == sym
        return RulePtr(self.rule, self.index+1)

    @property
    def is_satisfied(self):
        return self.index == len(self.rule.expansion)

    def __eq__(self, other):
        return self.rule == other.rule and self.index == other.index
    def __hash__(self):
        return hash((self.rule, self.index))


def pairs(lst):
    return zip(lst[:-1], lst[1:])

def update_set(set1, set2):
    copy = set(set1)
    set1 |= set2
    return set1 != copy

def calculate_sets(rules):
    """Calculate FOLLOW sets.

    Adapted from: http://lara.epfl.ch/w/cc09:algorithm_for_first_and_follow_sets"""
    symbols = {sym for rule in rules for sym in rule.expansion} | {rule.origin for rule in rules}
    symbols.add('$root')    # what about other unused rules?

    # foreach grammar rule X ::= Y(1) ... Y(k)
    # if k=0 or {Y(1),...,Y(k)} subset of NULLABLE then
    #   NULLABLE = NULLABLE union {X}
    # for i = 1 to k
    #   if i=1 or {Y(1),...,Y(i-1)} subset of NULLABLE then
    #     FIRST(X) = FIRST(X) union FIRST(Y(i))
    #   for j = i+1 to k
    #     if i=k or {Y(i+1),...Y(k)} subset of NULLABLE then
    #       FOLLOW(Y(i)) = FOLLOW(Y(i)) union FOLLOW(X)
    #     if i+1=j or {Y(i+1),...,Y(j-1)} subset of NULLABLE then
    #       FOLLOW(Y(i)) = FOLLOW(Y(i)) union FIRST(Y(j))
    # until none of NULLABLE,FIRST,FOLLOW changed in last iteration

    NULLABLE = set()
    FIRST = {}
    FOLLOW = {}
    for sym in symbols:
        FIRST[sym]={sym} if is_terminal(sym) else set()
        FOLLOW[sym]=set()

    changed = True
    while changed:
        changed = False

        for rule in rules:
            if set(rule.expansion) <= NULLABLE:
                if update_set(NULLABLE, {rule.origin}):
                    changed = True

            for i, sym in enumerate(rule.expansion):
                if set(rule.expansion[:i]) <= NULLABLE:
                    if update_set(FIRST[rule.origin], FIRST[sym]):
                        changed = True
                if i==len(rule.expansion)-1 or set(rule.expansion[i:]) <= NULLABLE:
                    if update_set(FOLLOW[sym], FOLLOW[rule.origin]):
                        changed = True

                for j in range(i+1, len(rule.expansion)):
                    if set(rule.expansion[i+1:j]) <= NULLABLE:
                        if update_set(FOLLOW[sym], FIRST[rule.expansion[j]]):
                            changed = True

    return FIRST, FOLLOW, NULLABLE


class GrammarAnalyzer(object):
    def __init__(self, rule_tuples, start_symbol, debug=False):
        self.start_symbol = start_symbol
        self.debug = debug
        rule_tuples = list(rule_tuples)
        rule_tuples.append(('$root', [start_symbol, '$end']))
        rule_tuples = [(t[0], t[1], None) if len(t)==2 else t for t in rule_tuples]

        self.rules = set()
        self.rules_by_origin = {o: [] for o, _x, _a in rule_tuples}
        for origin, exp, alias in rule_tuples:
            r =  Rule( origin, exp, alias )
            self.rules.add(r)
            self.rules_by_origin[origin].append(r)

        for r in self.rules:
            for sym in r.expansion:
                if not (is_terminal(sym) or sym in self.rules_by_origin):
                    raise GrammarError("Using an undefined rule: %s" % sym)

        self.init_state = self.expand_rule(start_symbol)

        self.FIRST, self.FOLLOW, self.NULLABLE = calculate_sets(self.rules)

    def expand_rule(self, rule):
        "Returns all init_ptrs accessible by rule (recursive)"
        init_ptrs = set()
        def _expand_rule(rule):
            assert not is_terminal(rule), rule

            for r in self.rules_by_origin[rule]:
                init_ptr = RulePtr(r, 0)
                init_ptrs.add(init_ptr)

                if r.expansion: # if not empty rule
                    new_r = init_ptr.next
                    if not is_terminal(new_r):
                        yield new_r

        _ = list(bfs([rule], _expand_rule))

        return fzset(init_ptrs)

    def _first(self, r):
        if is_terminal(r):
            return {r}
        else:
            return {rp.next for rp in self.expand_rule(r) if is_terminal(rp.next)}

