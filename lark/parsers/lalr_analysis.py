"""This module builds a LALR(1) transition-table for lalr_parser.py

For now, shift/reduce conflicts are automatically resolved as shifts.
"""

# Author: Erez Shinan (2017)
# Email : erezshin@gmail.com

import logging
from collections import defaultdict

from ..utils import classify, classify_bool, bfs, fzset, Serialize, Enumerator
from ..exceptions import GrammarError

from .grammar_analysis import GrammarAnalyzer, Terminal, RulePtr, LR0ItemSet
from ..grammar import Rule

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

        def step(state):
            _, unsat = classify_bool(state.closure, lambda rp: rp.is_satisfied)

            d = classify(unsat, lambda rp: rp.next)
            for sym, rps in d.items():
                kernel = {rp.advance(sym) for rp in rps}
                closure = set(kernel)

                for rp in kernel:
                    if not rp.is_satisfied and not rp.next.is_term:
                        closure |= self.expand_rule(rp.next, self.lr0_rules_by_origin)

                new_state = LR0ItemSet(kernel, closure)
                state.transitions[sym] = new_state
                yield new_state

            self.states.add(state)

        for _ in bfs(self.lr0_start_states.values(), step):
            pass

    def discover_lookaheads(self):
        # state -> rule -> set of lookaheads
        self.lookaheads = defaultdict(lambda: defaultdict(set))
        # state -> rule -> list of (set of lookaheads) to propagate to
        self.propagates = defaultdict(lambda: defaultdict(list))

        for s in self.lr0_start_states.values():
            for rp in s.kernel:
                self.lookaheads[s][rp].add(Terminal('$END'))

        # There is a 1 to 1 correspondance between LR0 and LALR1 states.
        # We calculate the lookaheads for LALR1 kernel items from the LR0 kernel items.
        # use a terminal that does not exist in the grammar
        t = Terminal('$#')
        for s in self.states:
            for rp in s.kernel:
                for rp2, la in self.generate_lr1_closure([(rp, t)]):
                    if rp2.is_satisfied:
                        continue
                    next_symbol = rp2.next
                    next_state = s.transitions[next_symbol]
                    rp3 = rp2.advance(next_symbol)
                    assert(rp3 in next_state.kernel)
                    x = self.lookaheads[next_state][rp3]
                    if la == t:
                        # we must propagate rp's lookaheads to rp3's lookahead set
                        self.propagates[s][rp].append(x)
                    else:
                        # this lookahead is "generated spontaneously" for rp3
                        x.add(la)

    def propagate_lookaheads(self):
        changed = True
        while changed:
            changed = False
            for s in self.states:
                for rp in s.kernel:
                    # from (from is a keyword)
                    f = self.lookaheads[s][rp]
                    # to
                    t = self.propagates[s][rp]
                    for x in t:
                        old = len(x)
                        x |= f
                        changed = changed or (len(x) != old)

    def generate_lalr1_states(self):
        # 1 to 1 correspondance between LR0 and LALR1 states
        # We must fetch the lookaheads we calculated,
        # to create the LALR1 kernels from the LR0 kernels.
        # Then, we generate the LALR1 states by taking the LR1 closure of the new kernel items.
        # map of LR0 states to LALR1 states
        m = {}
        for s in self.states:
            kernel = []
            for rp in s.kernel:
                las = self.lookaheads[s][rp]
                assert(len(las) > 0)
                for la in las:
                    kernel.append((rp, la))
            m[s] = self.generate_lr1_closure(kernel)

        self.states = {}
        for s, v in m.items():
            actions = {}
            for la, next_state in s.transitions.items():
                actions[la] = (Shift, next_state.closure)

            sat, _ = classify_bool(v, lambda x: x[0].is_satisfied)
            reductions = classify(sat, lambda x: x[1], lambda x: x[0])
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

        end_states = {}
        for s in self.states:
            for rp in s:
                for start in self.lr0_start_states:
                    if rp.rule.origin.name == ('$root_' + start) and rp.is_satisfied:
                        assert(not start in end_states)
                        end_states[start] = s

        self._parse_table = ParseTable(self.states, {start: state.closure for start, state in self.lr0_start_states.items()}, end_states)

        if self.debug:
            self.parse_table = self._parse_table
        else:
            self.parse_table = IntParseTable.from_ParseTable(self._parse_table)

    def generate_lr1_closure(self, kernel):
        closure = set()

        q = list(kernel)
        while len(q) > 0:
            rp, la = q.pop()
            if (rp, la) in closure:
                continue
            closure.add((rp, la))

            if rp.is_satisfied:
                continue
            if rp.next.is_term:
                continue

            l = []
            i = rp.index + 1
            n = len(rp.rule.expansion)
            while i < n:
                s = rp.rule.expansion[i]
                l.extend(self.FIRST.get(s, []))
                if not s in self.NULLABLE:
                    break
                i += 1

            # if all of rp.rule.expansion[rp.index + 1:] were nullable:
            if i == n:
                l.append(la)

            for r in self.lr0_rules_by_origin[rp.next]:
                for s in l:
                    q.append((RulePtr(r, 0), s))

        return closure
