
from ..utils import bfs, fzset, classify
from ..common import GrammarError, is_terminal
from ..grammar import Rule


class RulePtr(object):
    __slots__ = ('rule', 'index')

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


def update_set(set1, set2):
    if not set2:
        return False

    copy = set(set1)
    set1 |= set2
    return set1 != copy

def calculate_sets(rules):
    """Calculate FOLLOW sets.

    Adapted from: http://lara.epfl.ch/w/cc09:algorithm_for_first_and_follow_sets"""
    symbols = {sym for rule in rules for sym in rule.expansion} | {rule.origin for rule in rules}

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

    # Calculate NULLABLE and FIRST
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

    # Calculate FOLLOW
    changed = True
    while changed:
        changed = False

        for rule in rules:
            for i, sym in enumerate(rule.expansion):
                if i==len(rule.expansion)-1 or set(rule.expansion[i:]) <= NULLABLE:
                    if update_set(FOLLOW[sym], FOLLOW[rule.origin]):
                        changed = True

                for j in range(i+1, len(rule.expansion)):
                    if set(rule.expansion[i+1:j]) <= NULLABLE:
                        if update_set(FOLLOW[sym], FIRST[rule.expansion[j]]):
                            changed = True

    return FIRST, FOLLOW, NULLABLE


class GrammarAnalyzer(object):
    def __init__(self, parser_conf, debug=False):
        self.debug = debug

        rules = parser_conf.rules + [Rule('$root', [parser_conf.start, '$END'])]
        self.rules_by_origin = classify(rules, lambda r: r.origin)

        assert len(rules) == len(set(rules))
        for r in rules:
            for sym in r.expansion:
                if not (is_terminal(sym) or sym in self.rules_by_origin):
                    raise GrammarError("Using an undefined rule: %s" % sym) # TODO test validation

        self.start_state = self.expand_rule('$root')

        self.FIRST, self.FOLLOW, self.NULLABLE = calculate_sets(rules)

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

        for _ in bfs([rule], _expand_rule):
            pass

        return fzset(init_ptrs)

    def _first(self, r):
        if is_terminal(r):
            return {r}
        else:
            return {rp.next for rp in self.expand_rule(r) if is_terminal(rp.next)}

