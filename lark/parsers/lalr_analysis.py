"""This module builds a LALR(1) transition-table for lalr_parser.py

For now, shift/reduce conflicts are automatically resolved as shifts.
"""

# Author: Erez Shinan (2017)
# Email : erezshin@gmail.com

import logging
from collections import defaultdict

from ..utils import classify, classify_bool, bfs, fzset, Serialize, Enumerator
from ..exceptions import GrammarError

from .grammar_analysis import GrammarAnalyzer, Terminal
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

    def compute_lookahead(self):

        self.states = {}
        def step(state):
            lookahead = defaultdict(list)
            sat, unsat = classify_bool(state, lambda rp: rp.is_satisfied)
            for rp in sat:
                for term in self.FOLLOW.get(rp.rule.origin, ()):
                    lookahead[term].append((Reduce, rp.rule))

            d = classify(unsat, lambda rp: rp.next)
            for sym, rps in d.items():
                rps = {rp.advance(sym) for rp in rps}

                for rp in set(rps):
                    if not rp.is_satisfied and not rp.next.is_term:
                        rps |= self.expand_rule(rp.next)

                new_state = fzset(rps)
                lookahead[sym].append((Shift, new_state))
                yield new_state

            for k, v in lookahead.items():
                if len(v) > 1:
                    if self.debug:
                        logging.warning("Shift/reduce conflict for terminal %s:  (resolving as shift)", k.name)
                        for act, arg in v:
                            logging.warning(' * %s: %s', act, arg)
                    for x in v:
                        # XXX resolving shift/reduce into shift, like PLY
                        # Give a proper warning
                        if x[0] is Shift:
                            lookahead[k] = [x]

            for k, v in lookahead.items():
                if not len(v) == 1:
                    raise GrammarError("Collision in %s: %s" %(k, ', '.join(['\n  * %s: %s' % x for x in v])))

            self.states[state] = {k.name:v[0] for k, v in lookahead.items()}

        for _ in bfs(self.start_states.values(), step):
            pass

        self._parse_table = ParseTable(self.states, self.start_states, self.end_states)

        if self.debug:
            self.parse_table = self._parse_table
        else:
            self.parse_table = IntParseTable.from_ParseTable(self._parse_table)

