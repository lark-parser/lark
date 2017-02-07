from collections import defaultdict, deque

from ..utils import classify, classify_bool, bfs, fzset
from ..common import GrammarError, is_terminal

ACTION_SHIFT = 0

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
        return '<%s : %s>' % (self.origin, ' '.join(self.expansion))

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

class GrammarAnalyzer(object):
    def __init__(self, rule_tuples, start_symbol):
        self.start_symbol = start_symbol
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

    def expand_rule(self, rule):
        "Returns all init_ptrs accessible by rule (recursive)"
        init_ptrs = set()
        def _expand_rule(rule):
            assert not is_terminal(rule)

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

    def _calc(self):
        """Calculate FOLLOW sets.

        Adapted from: http://lara.epfl.ch/w/cc09:algorithm_for_first_and_follow_sets"""
        symbols = {sym for rule in self.rules for sym in rule.expansion} | {rule.origin for rule in self.rules}
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

            for rule in self.rules:
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

        self.FOLLOW = FOLLOW

    def analyze(self):
        self._calc()

        self.states = {}
        def step(state):
            lookahead = defaultdict(list)
            sat, unsat = classify_bool(state, lambda rp: rp.is_satisfied)
            for rp in sat:
                for term in self.FOLLOW.get(rp.rule.origin, ()):
                    lookahead[term].append(('reduce', rp.rule))

            d = classify(unsat, lambda rp: rp.next)
            for sym, rps in d.items():
                rps = {rp.advance(sym) for rp in rps}

                for rp in set(rps):
                    if not rp.is_satisfied and not is_terminal(rp.next):
                        rps |= self.expand_rule(rp.next)

                lookahead[sym].append(('shift', fzset(rps)))
                yield fzset(rps)

            for k, v in lookahead.items():
                if len(v) > 1:
                    for x in v:
                        # XXX resolving shift/reduce into shift, like PLY
                        # Give a proper warning
                        if x[0] == 'shift':
                            lookahead[k] = [x]

            for k, v in lookahead.items():
                assert len(v) == 1, ("Collision", k, v)

            self.states[state] = {k:v[0] for k, v in lookahead.items()}

        x = list(bfs([self.init_state], step))

        # --
        self.enum = list(self.states)
        self.enum_rev = {s:i for i,s in enumerate(self.enum)}
        self.states_idx = {}

        for s, la in self.states.items():
            la = {k:(ACTION_SHIFT, self.enum_rev[v[1]]) if v[0]=='shift' else v for k,v in la.items()}
            self.states_idx[ self.enum_rev[s] ] = la


        self.init_state_idx = self.enum_rev[self.init_state]

