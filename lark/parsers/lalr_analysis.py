"""This module builds a LALR(1) transition-table for lalr_parser.py

For now, shift/reduce conflicts are automatically resolved as shifts.
"""

# Author: Erez Shinan (2017)
# Email : erezshin@gmail.com

import logging
from collections import defaultdict

from ..utils import classify, classify_bool, bfs, fzset
from ..common import GrammarError, is_terminal

from .grammar_analysis import GrammarAnalyzer

ACTION_SHIFT = 0

class LALR_Analyzer(GrammarAnalyzer):

    def compute_lookahead(self):

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
                    if self.debug:
                        logging.warn("Shift/reduce conflict for %s: %s. Resolving as shift.", k, v)
                    for x in v:
                        # XXX resolving shift/reduce into shift, like PLY
                        # Give a proper warning
                        if x[0] == 'shift':
                            lookahead[k] = [x]

            for k, v in lookahead.items():
                if not len(v) == 1:
                    raise GrammarError("Collision in %s: %s" %(k, v))

            self.states[state] = {k:v[0] for k, v in lookahead.items()}

        for _ in bfs([self.init_state], step):
            pass

        # --
        self.enum = list(self.states)
        self.enum_rev = {s:i for i,s in enumerate(self.enum)}
        self.states_idx = {}

        for s, la in self.states.items():
            la = {k:(ACTION_SHIFT, self.enum_rev[v[1]]) if v[0]=='shift'
                    else (v[0], (v[1], len(v[1].expansion)))    # Reduce
                  for k,v in la.items()}
            self.states_idx[ self.enum_rev[s] ] = la


        self.init_state_idx = self.enum_rev[self.init_state]
