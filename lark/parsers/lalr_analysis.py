"""This module builds a LALR(1) transition-table for lalr_parser.py

For now, shift/reduce conflicts are automatically resolved as shifts.
"""

# Author: Erez Shinan (2017)
# Email : erezshin@gmail.com

import logging
from collections import defaultdict, deque

from ..utils import classify, classify_bool, bfs, fzset, Serialize, Enumerator
from ..exceptions import GrammarError

from .grammar_analysis import GrammarAnalyzer, Terminal, RulePtr, LR0ItemSet
from ..grammar import Rule
from . import grammar_analysis

import time

###{standalone

class Action:
    def __init__(self, name):
        self.name = name
    def __str__(self):
        return self.name
    def __repr__(self):
        return str(self)

Shift = Action('Shift')
Reduce = Action('Reduce')

t_set_0 = 0
t_set_1 = 0
t_expand = 0
t_rules = 0
t_append = 0
t_z = 0
t_begin = 0
t_count = 0
t_call = 0

class ParseTable:
    def __init__(self, states, start_states, end_states):
        self.states = states
        self.start_states = start_states
        self.end_states = end_states

    def serialize(self, memo):
        tokens = Enumerator()
        rules = Enumerator()

        states = {
            state: {tokens.get(token): ((1, arg.serialize(memo)) if action is Reduce else (0, arg))
                    for token, (action, arg) in actions.items()}
            for state, actions in self.states.items()
        }

        return {
            'tokens': tokens.reversed(),
            'states': states,
            'start_states': self.start_states,
            'end_states': self.end_states,
        }

    @classmethod
    def deserialize(cls, data, memo):
        tokens = data['tokens']
        states = {
            state: {tokens[token]: ((Reduce, Rule.deserialize(arg, memo)) if action==1 else (Shift, arg))
                    for token, (action, arg) in actions.items()}
            for state, actions in data['states'].items()
        }
        return cls(states, data['start_states'], data['end_states'])


class IntParseTable(ParseTable):

    @classmethod
    def from_ParseTable(cls, parse_table):
        enum = list(parse_table.states)
        state_to_idx = {s:i for i,s in enumerate(enum)}
        int_states = {}

        for s, la in parse_table.states.items():
            la = {k:(v[0], state_to_idx[v[1]]) if v[0] is Shift else v
                  for k,v in la.items()}
            int_states[ state_to_idx[s] ] = la


        start_states = {start:state_to_idx[s] for start, s in parse_table.start_states.items()}
        end_states = {start:state_to_idx[s] for start, s in parse_table.end_states.items()}
        return cls(int_states, start_states, end_states)

###}

class LALR_Analyzer(GrammarAnalyzer):

    def generate_lr0_states(self):
        self.states = set()
        # map of kernels to LR0ItemSets
        cache = {}

        def step(state):
            _, unsat = classify_bool(state.closure, lambda rp: rp.is_satisfied)

            d = classify(unsat, lambda rp: rp.next)
            for sym, rps in d.items():
                kernel = fzset({rp.advance(sym) for rp in rps})
                new_state = cache.get(kernel, None)
                if new_state is None:
                    closure = set(kernel)
                    for rp in kernel:
                        if not rp.is_satisfied and not rp.next.is_term:
                            closure |= self.expand_rule(rp.next, self.lr0_rules_by_origin)
                    new_state = LR0ItemSet(kernel, closure)
                    cache[kernel] = new_state

                state.transitions[sym] = new_state
                yield new_state

            self.states.add(state)

        for _ in bfs(self.lr0_start_states.values(), step):
            pass

    def discover_lookaheads(self):
        # lookaheads is now a member of LR0ItemSet, so don't need to look up a dictionary here
        # state -> rule -> set of lookaheads
        #self.lookaheads = defaultdict(lambda: defaultdict(set))
        # state -> rule -> list of (set of lookaheads) to propagate to
        #self.propagates = defaultdict(lambda: defaultdict(list))
        self.propagates = {}

        t0 = time.time()

        t = Terminal('$END')
        for s in self.lr0_start_states.values():
            for rp in s.kernel:
                #self.lookaheads[s][rp].add(Terminal('$END'))
                s.lookaheads[rp].add(t)

        t_closure = 0

        # There is a 1 to 1 correspondance between LR0 and LALR1 states.
        # We calculate the lookaheads for LALR1 kernel items from the LR0 kernel items.
        # use a terminal that does not exist in the grammar
        t = Terminal('$#')
        for s in self.states:
            p = {}
            self.propagates[s] = p
            for rp in s.kernel:
                q = []
                p[rp] = q
                t2 = time.time()
                z = self.generate_lr1_closure([rp.lookahead(t)], time.time())
                t3 = time.time()
                t_closure += t3 - t2
                #for rp2, la in self.generate_lr1_closure([(rp, t)], time.time()):
                for rp2_la in z:
                    rp2 = rp2_la.rp
                    la = rp2_la.la
                    if rp2.is_satisfied:
                        continue
                    next_symbol = rp2.next
                    next_state = s.transitions[next_symbol]
                    rp3 = rp2.advance(next_symbol)
                    assert(rp3 in next_state.kernel)
                    #x = self.lookaheads[next_state][rp3]
                    x = next_state.lookaheads[rp3]
                    if la == t:
                        # we must propagate rp's lookaheads to rp3's lookahead set
                        q.append(x)
                    else:
                        # this lookahead is "generated spontaneously" for rp3
                        x.add(la)

        t1 = time.time()
        print('Discovering took {:.3f} (generating closure), {:.3f} (total)'.format(t_closure, t1 - t0))

    def propagate_lookaheads(self):
        changed = True
        while changed:
            changed = False
            for s in self.states:
                for rp in s.kernel:
                    # from (from is a keyword)
                    #f = self.lookaheads[s][rp]
                    f = s.lookaheads[rp]
                    # to
                    t = self.propagates[s][rp]
                    for x in t:
                        old = len(x)
                        x |= f
                        changed = changed or (len(x) != old)

    def generate_lalr1_states(self):
        t0 = time.time()
        # 1 to 1 correspondance between LR0 and LALR1 states
        # We must fetch the lookaheads we calculated,
        # to create the LALR1 kernels from the LR0 kernels.
        # Then, we generate the LALR1 states by taking the LR1 closure of the new kernel items.
        # map of LR0 states to LALR1 states
        m = {}
        t_closure = 0
        z = 0
        for s in self.states:
            z = max(z, len(s.closure))
            kernel = []
            for rp in s.kernel:
                #las = self.lookaheads[s][rp]
                las = s.lookaheads[rp]
                assert(len(las) > 0)
                for la in las:
                    kernel.append(rp.lookahead(la))
            t0_0 = time.time()
            m[s] = self.generate_lr1_closure(kernel, time.time())
            t0_1 = time.time()
            t_closure += t0_1 - t0_0

        print('Generating lalr1 closure for lalr kernels took {:.3f}'.format(t_closure))
        print('Max lr0 state size was {}'.format(z))

        t1 = time.time()

        self.states = {}
        for s, v in m.items():
            actions = {}
            for la, next_state in s.transitions.items():
                actions[la] = (Shift, next_state.closure)

            sat, _ = classify_bool(v, lambda x: x.rp.is_satisfied)
            reductions = classify(sat, lambda x: x.la, lambda x: x.rp)
            for la, rps in reductions.items():
                if len(rps) > 1:
                    raise GrammarError("Collision in %s: %s" % (la, ', '.join([ str(r.rule) for r in rps ])))
                if la in actions:
                    if self.debug:
                        logging.warning("Shift/reduce conflict for terminal %s:  (resolving as shift)", la.name)
                        logging.warning(' * %s', str(rps[0]))
                else:
                    actions[la] = (Reduce, rps[0].rule)

            self.states[s.closure] = {k.name: v for k, v in actions.items()}

        t2 = time.time()

        end_states = {}
        for s in self.states:
            for rp in s:
                for start in self.lr0_start_states:
                    if rp.rule.origin.name == ('$root_' + start) and rp.is_satisfied:
                        assert(not start in end_states)
                        end_states[start] = s

        t3 = time.time()

        self._parse_table = ParseTable(self.states, {start: state.closure for start, state in self.lr0_start_states.items()}, end_states)

        t4 = time.time()

        if self.debug:
            self.parse_table = self._parse_table
        else:
            self.parse_table = IntParseTable.from_ParseTable(self._parse_table)

        t5 = time.time()

        print(('Generating lalr1 states took ' + ', '.join([ '{:.3f}' ] * 5)).format(t1 - t0, t2 - t1, t3 - t2, t4 - t3, t5 - t4))
        print('Generating firsts took {:.3f} (time actually calculating), {:.3f} (end to end), {:.3f} (just function call)'.format(grammar_analysis.t_firsts, grammar_analysis.t_xy, grammar_analysis.t_call))

    def generate_lr1_closure(self, kernel, t_caller):
        global t_call
        global t_set_0
        global t_set_1
        global t_expand
        global t_rules
        global t_append
        global t_z
        global t_begin
        global t_count

        t_start = time.time()
        t_call += t_start - t_caller

        # cache the results of this function
        # not many hits, no noticeable performance improvement
        '''
        k = fzset(kernel)
        cached = self.lr1_cache.get(k, None)
        if not cached is None:
            return cached
        '''

        closure = set()
        closure_hash = {}

        y = 0

        q = list(kernel)
        while len(q) > 0:
            t_a = time.time()
            rp_la = q.pop()
            #rp_la_hash = hash(rp_la)
            t0 = time.time()
            t_begin += t0 - t_a
            # try to manually maintain hashtable,
            # as a set of just hashes (ints) was notably faster
            '''
            if rp_la_hash in closure_hash:
                if rp_la in closure_hash[rp_la_hash]:
                    t0_0 = time.time()
                    t_set_0 += t0_0 - t0
                    continue
                t0_0 = time.time()
                t_set_0 += t0_0 - t0
            else:
                closure_hash[rp_la_hash] = []
            '''
            if rp_la in closure:
                t0_0 = time.time()
                t_set_0 += t0_0 - t0
                continue
            t0_0 = time.time()
            closure.add(rp_la)
            #closure_hash[rp_la_hash].append(rp_la)
            t1 = time.time()
            t_set_0 += t0_0 - t0
            t_set_1 += t1 - t0_0
            rp = rp_la.rp
            la = rp_la.la

            if rp.is_satisfied:
                continue
            if rp.next.is_term:
                continue

            t2 = time.time()

            # cache these calculations inside each RulePtr
            # see grammar_analysis.py:79
            l = []
            '''
            i = rp.index + 1
            n = len(rp.rule.expansion)
            l2_i = self.lr1_cache2.get((rp.rule, i), None)
            l2 = []
            if l2_i is None:
                while i < n:
                    s = rp.rule.expansion[i]
                    l2.extend(self.FIRST.get(s, []))
                    if not s in self.NULLABLE:
                        break
                    i += 1
                self.lr1_cache2[(rp.rule, i)] = (l2, i)
            else:
                l2 = l2_i[0]
                i = l2_i[1]

            l.extend(l2)
            '''
            # this function call seems really slow (see grammar_analysis.t_call above)
            # tried making it not a method call so don't need to look up vtable
            # still equally slow
            l2, nullable = rp.first(rp.index + 1, self.FIRST, self.NULLABLE, time.time())
            #l2, nullable = grammar_analysis.first(rp, rp.index + 1, self.FIRST, self.NULLABLE, time.time())
            #l.extend(l2)
            l = l2
            t3 = time.time()

            t_expand += t3 - t2

            # if we don't modify l2 and add an extra check in the loop below,
            # we don't have to copy it
            # if all of rp.rule.expansion[rp.index + 1:] were nullable:
            #if nullable:
            #    l.append(la)

            t4 = time.time()
            x = rp.next_rules_by_origin(self.lr0_rules_by_origin)
            t5 = time.time()

            # usually between 20-60? seen as high as ~175
            y = max(y, len(x) * len(l))
            #print('adding {} * {} rules to closure max {}'.format(len(x), len(l), y))
            for r in x:
                for s in l:
                    # cache RulePtr(r, 0) in r (no duplicate RulePtr objects)
                    # cache r._rp in _rp (1 less object property lookup?)
                    _rp = r._rp
                    if _rp is None:
                        _rp = RulePtr(r, 0)
                        r._rp = _rp
                    q.append(_rp.lookahead(s))
                    #q.append((r._rp, s))
                if nullable:
                    _rp = r._rp
                    if _rp is None:
                        _rp = RulePtr(r, 0)
                        r._rp = _rp
                    q.append(_rp.lookahead(la))
                    #q.append((r._rp, la))

            t6 = time.time()
            t_rules += t5 - t4
            t_append += t6 - t5

        #self.lr1_cache[k] = closure

        t_end = time.time()
        t_z += t_end - t_start

        t_count += 1

        if t_count % 1000 == 0:
            print('\tGenerating lr1 closure took begin {:.3f}, set contains {:.3f}, set add {:.3f}, get first {:.3f}'.format(t_begin, t_set_0, t_set_1, t_expand))
            print('\tget next rules {:.3f}, append rules {:.3f}, total {:.3f}, call time {:.3f}, count {}'.format(t_rules, t_append, t_z, t_call, t_count))
            print('\tmax number of appends {}'.format(y))

        return closure
