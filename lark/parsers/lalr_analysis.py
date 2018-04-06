"""This module builds a LALR(1) transition-table for lalr_parser.py

For now, shift/reduce conflicts are automatically resolved as shifts.
"""

# Author: Erez Shinan (2017)
# Email : erezshin@gmail.com

import logging
from collections import defaultdict
from array import array

from ..utils import classify, classify_bool, bfs, fzset
from ..common import GrammarError, is_terminal

from .grammar_analysis import GrammarAnalyzer

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
    def __init__(self, states, start_state, end_state):
        self.states = states
        self.start_state = start_state
        self.end_state = end_state


class ArrayParseTable(ParseTable):
    """
    Stores the parse table in a array of 16bit ints with all the states
    packed one after the other in the following structure:

        num_tokens [ token_id atom ]*

    The atom has its highest bit set if it's a reduce action.
    """

    class StateProxy(object):
        __slots__ = ('context', 'offset', 'cache')

        def __init__(self, context, offset):
            self.context = context
            self.offset = offset
            self.cache = {}

        def keys(self):
            ofs = self.offset
            table = self.context.table
            inv_tokens = {v:k for k,v in self.context.tokens.items()}
            length = table[ofs]
            ofs += 1
            while length > 0:
                yield inv_tokens[ table[ofs] ]
                ofs += 2
                length -= 1

        def values(self):
            for token in self.keys():
                yield self[token]

        def items(self):
            for token in self.keys():
                yield (token, self[token])

        def __getitem__(self, token):
            if token in self.cache:
                return self.cache[token]

            token_idx = self.context.tokens[token]
            table = self.context.table
            ofs = self.offset

            # tokens are sorted so use a binary search to find it
            lo = 0
            hi = table[ofs]
            ofs += 1
            while lo < hi:
                mid = (lo+hi)//2
                value = table[ofs + mid*2]
                if value < token_idx:
                    lo = mid + 1
                elif value > token_idx:
                    hi = mid
                else:
                    self.cache[token] = self._unpack(table[ofs + mid*2 + 1])
                    return self.cache[token]
            else:
                raise KeyError(token)

        def _unpack(self, atom):
            if atom & 0x8000:
                atom &= ~0x8000
                return Reduce, self.context.idx_rules[atom]
            else:
                return Shift, atom



    def __init__(self, states, start_state, end_state):
        states_idx = dict( (s, i) for i,s in enumerate(states.keys()) )

        self.start_state = states_idx[start_state]
        self.end_state = states_idx[end_state]

        self.table = table = array('H')  # unsigned 16bit ints

        self.tokens = tokens = {}
        idx_tokens = []
        rules = {}
        self.idx_rules = idx_rules = []

        self.states = {}
        for state, productions in states.items():
            # Create state proxy for the current offset
            self.states[ states_idx[state] ] = ArrayParseTable.StateProxy(self, len(table))

            # Prefix with the length of the state
            table.append(len(productions))

            # Sort the tokens based on the assigned index, indexing those
            # that we haven't seen before
            subtokens = []
            for token in productions:
                if token not in tokens:
                    tokens[token] = len(idx_tokens)
                    idx_tokens.append(token)

                subtokens.append(tokens[token])

            subtokens.sort()

            for token_idx in subtokens:
                token = idx_tokens[token_idx]
                value = productions[token]

                table.append(token_idx)

                if value[0] is Shift:
                    table.append(states_idx[ value[1] ])
                else:
                    if value[1] not in rules:
                        rules[ value[1] ] = len(idx_rules)
                        idx_rules.append(value[1])

                    ptr = rules[ value[1] ] | 0x8000
                    table.append(ptr)


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

        start_state = state_to_idx[parse_table.start_state]
        end_state = state_to_idx[parse_table.end_state]
        return cls(int_states, start_state, end_state)


class LALR_Analyzer(GrammarAnalyzer):

    def compute_lookahead(self):
        self.end_states = []

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
                    if not rp.is_satisfied and not is_terminal(rp.next):
                        rps |= self.expand_rule(rp.next)

                new_state = fzset(rps)
                lookahead[sym].append((Shift, new_state))
                if sym == '$END':
                    self.end_states.append( new_state )
                yield new_state

            for k, v in lookahead.items():
                if len(v) > 1:
                    if self.debug:
                        logging.warn("Shift/reduce conflict for %s: %s. Resolving as shift.", k, v)
                    for x in v:
                        # XXX resolving shift/reduce into shift, like PLY
                        # Give a proper warning
                        if x[0] is Shift:
                            lookahead[k] = [x]

            for k, v in lookahead.items():
                if not len(v) == 1:
                    raise GrammarError("Collision in %s: %s" %(k, ', '.join(['\n  * %s: %s' % x for x in v])))

            self.states[state] = {k:v[0] for k, v in lookahead.items()}

        for _ in bfs([self.start_state], step):
            pass

        self.end_state ,= self.end_states

        self._parse_table = ParseTable(self.states, self.start_state, self.end_state)

        if self.debug:
            self.parse_table = self._parse_table
        elif self.parser_conf.parsetable_class:
            self.parse_table = self.parser_conf.parsetable_class(self.states, self.start_state, self.end_state)
        else:
            self.parse_table = IntParseTable.from_ParseTable(self._parse_table)
