from collections import Counter, defaultdict

from ..utils import bfs, fzset, classify
from ..exceptions import GrammarError
from ..grammar import Rule, Terminal, NonTerminal
import time

t_firsts = 0
t_xy = 0
t_call = 0
cache_hits = 0
cache_misses = 0

# used to be just a tuple (rp, la)
# but by making it an object,
# the hash and equality become trivial
# (slightly faster for sets which are hashtables?)
class RulePtrLookahead(object):
    __slots__ = 'rp', 'la'

    def __init__(self, rp, la):
        self.rp = rp
        self.la = la

class RulePtr(object):
    __slots__ = ('rule', 'index', '_advance', '_lookaheads', '_next_rules_by_origin', '_first')

    def __init__(self, rule, index):
        assert isinstance(rule, Rule)
        assert index <= len(rule.expansion)
        self.rule = rule
        self.index = index
        #self._hash = hash((self.rule, self.index))
        #self._hash = None
        self._advance = None
        self._lookaheads = {}
        self._next_rules_by_origin = None
        self._first = None

    def __repr__(self):
        before = [x.name for x in self.rule.expansion[:self.index]]
        after = [x.name for x in self.rule.expansion[self.index:]]
        return '<%s : %s * %s>' % (self.rule.origin.name, ' '.join(before), ' '.join(after))

    @property
    def next(self):
        return self.rule.expansion[self.index]

    # don't create duplicate RulePtrs
    def advance(self, sym):
        assert self.next == sym
        a = self._advance
        if a is None:
            a = RulePtr(self.rule, self.index + 1)
            self._advance = a
        return a

    @property
    def is_satisfied(self):
        return self.index == len(self.rule.expansion)

    def lookahead(self, la):
        rp_la = self._lookaheads.get(la, None)
        if rp_la is None:
            rp_la = RulePtrLookahead(self, la)
            self._lookaheads[la] = rp_la
        return rp_la

    def next_rules_by_origin(self, rules_by_origin):
        n = self._next_rules_by_origin
        if n is None:
            n = rules_by_origin[self.next]
            self._next_rules_by_origin = n
        return n

    # recursive form of lalr_analyis.py:343 (which is easier to understand IMO)
    # normally avoid recursion but this allows us to cache
    # each intermediate step in a corresponding RulePtr
    def first(self, i, firsts, nullable, t):
        global cache_hits
        global cache_misses
        global t_firsts
        global t_xy
        global t_call
        t_call += time.time() - t
        n = len(self.rule.expansion)
        if i == n:
            return ([], True)
        x = self._first
        t_x = time.time()
        if x is None:
            t0 = time.time()
            t_y = time.time()
            cache_misses += 1
            s = self.rule.expansion[i]
            l = list(firsts.get(s, []))
            b = (s in nullable)
            if b:
                t1 = time.time()
                t_firsts += t1 - t0
                l_b_2 = self.advance(s).first(i + 1, firsts, nullable, time.time())
                #l_b_2 = first(self.advance(self.next), i + 1, firsts, nullable, time.time())
                t0 = time.time()
                l.extend(l_b_2[0])
                b = l_b_2[1]
            x = (l, b)
            self._first = x
            t1 = time.time()
            t_firsts += t1 - t0
        else:
            t_y = time.time()
            cache_hits += 1
        t_xy += t_y - t_x
        return x

    # optimizations were made so that there should never be
    # two distinct equal RulePtrs
    # should help set/hashtable lookups?
    '''
    def __eq__(self, other):
        return self.rule == other.rule and self.index == other.index
    def __hash__(self):
        return self._hash
    '''


class LR0ItemSet(object):
    __slots__ = ('kernel', 'closure', 'transitions', 'lookaheads', '_hash')

    def __init__(self, kernel, closure):
        self.kernel = fzset(kernel)
        self.closure = fzset(closure)
        self.transitions = {}
        self.lookaheads = defaultdict(set)
        #self._hash = hash(self.kernel)

    # state generation ensures no duplicate LR0ItemSets
    '''
    def __eq__(self, other):
        return self.kernel == other.kernel

    def __hash__(self):
        return self._hash
    '''

    def __repr__(self):
        return '{%s | %s}' % (', '.join([repr(r) for r in self.kernel]), ', '.join([repr(r) for r in self.closure]))


def update_set(set1, set2):
    if not set2 or set1 > set2:
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
        FIRST[sym]={sym} if sym.is_term else set()
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
                else:
                    break

    # Calculate FOLLOW
    changed = True
    while changed:
        changed = False

        for rule in rules:
            for i, sym in enumerate(rule.expansion):
                if i==len(rule.expansion)-1 or set(rule.expansion[i+1:]) <= NULLABLE:
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

        root_rules = {start: Rule(NonTerminal('$root_' + start), [NonTerminal(start), Terminal('$END')])
                      for start in parser_conf.start}

        rules = parser_conf.rules + list(root_rules.values())
        self.rules_by_origin = classify(rules, lambda r: r.origin)

        if len(rules) != len(set(rules)):
            duplicates = [item for item, count in Counter(rules).items() if count > 1]
            raise GrammarError("Rules defined twice: %s" % ', '.join(str(i) for i in duplicates))

        for r in rules:
            for sym in r.expansion:
                if not (sym.is_term or sym in self.rules_by_origin):
                    raise GrammarError("Using an undefined rule: %s" % sym) # TODO test validation

        self.start_states = {start: self.expand_rule(root_rule.origin)
                             for start, root_rule in root_rules.items()}

        self.end_states = {start: fzset({RulePtr(root_rule, len(root_rule.expansion))})
                           for start, root_rule in root_rules.items()}

        lr0_root_rules = {start: Rule(NonTerminal('$root_' + start), [NonTerminal(start)])
                for start in parser_conf.start}

        lr0_rules = parser_conf.rules + list(lr0_root_rules.values())
        assert(len(lr0_rules) == len(set(lr0_rules)))

        self.lr0_rules_by_origin = classify(lr0_rules, lambda r: r.origin)

        # cache RulePtr(r, 0) in r (no duplicate RulePtr objects)
        for root_rule in lr0_root_rules.values():
            root_rule._rp = RulePtr(root_rule, 0)
        self.lr0_start_states = {start: LR0ItemSet([root_rule._rp], self.expand_rule(root_rule.origin, self.lr0_rules_by_origin))
                for start, root_rule in lr0_root_rules.items()}

        self.FIRST, self.FOLLOW, self.NULLABLE = calculate_sets(rules)

        # unused, did not help
        self.lr1_cache = {}
        self.lr1_cache2 = {}

    def expand_rule(self, source_rule, rules_by_origin=None):
        "Returns all init_ptrs accessible by rule (recursive)"

        if rules_by_origin is None:
            rules_by_origin = self.rules_by_origin

        init_ptrs = set()
        def _expand_rule(rule):
            assert not rule.is_term, rule

            for r in rules_by_origin[rule]:
                # don't create duplicate RulePtr objects
                init_ptr = r._rp
                if init_ptr is None:
                    init_ptr = RulePtr(r, 0)
                    r._rp = init_ptr
                init_ptrs.add(init_ptr)

                if r.expansion: # if not empty rule
                    new_r = init_ptr.next
                    if not new_r.is_term:
                        yield new_r

        for _ in bfs([source_rule], _expand_rule):
            pass

        return fzset(init_ptrs)
