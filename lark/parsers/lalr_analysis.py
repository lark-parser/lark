"""This module builds a LALR(1) transition-table for lalr_parser.py

For now, shift/reduce conflicts are automatically resolved as shifts.
"""

# Author: Erez Shinan (2017)
# Email : erezshin@gmail.com

import logging
import sys
from bisect import bisect_left, insort_left
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

        ( token_id+ value+ )+

    Values have its highest bit set if it's a reduce action.
    """

    class StateProxy(object):
        __slots__ = ('tokens', 'idx_rules', 'table', 'offset', 'length')

        def __init__(self, tokens, idx_rules, table, offset, length):
            self.tokens = tokens
            self.idx_rules = idx_rules
            self.table = table
            self.offset = offset
            self.length = length

        def iterkeys(self):
            inv_tokens = {v:k for k,v in self.tokens.items()}
            offset = self.offset
            while offset < self.offset + self.length:
                yield inv_tokens[ self.table[offset] ]
                offset += 1

        def itervalues(self):
            for token in self.iterkeys(): yield token

        def iteritems(self):
            for token in self.iterkeys(): yield (token, self[token])

        items = lambda self: list(self.iteritems())
        keys = lambda self: list(self.iterkeys())
        values = lambda self: list(self.itervalues())

        if sys.version_info >= (3, 0):
            keys = StateProxy.iterkeys
            values = StateProxy.itervalues
            items = StateProxy.iteritems

        def __getitem__(self, token):
            token_idx = self.tokens[token]
            table = self.table
            offset = self.offset
            offset_end = offset + self.length

            idx = bisect_left(table, token_idx, offset, offset_end)
            if idx == offset_end or table[idx] != token_idx:
                raise KeyError(token)

            atom = table[idx + self.length]
            if atom & 0x8000:
                atom &= ~0x8000
                return Reduce, self.idx_rules[atom]
            else:
                return Shift, atom


    def __init__(self, states, start_state, end_state):
        idx_states = dict( (s, i) for i,s in enumerate(states.keys()) )
        assert len(idx_states) < 0x8000, "ArrayParseTable doesn't support more than 32767 states"

        self.start_state = idx_states[start_state]
        self.end_state = idx_states[end_state]

        table = array('H')  # unsigned 16bit ints
        tokens = tokens = {}
        idx_tokens = []
        rules = {}
        idx_rules = []

        self.states = {}
        for state, productions in states.items():
            # Sort the tokens based on the assigned index
            subtokens = []
            for token in productions:
                if token not in tokens:
                    tokens[token] = len(idx_tokens)
                    idx_tokens.append(token)
                    assert len(idx_tokens) < 0xFFFF, "ArrayParseTable doesn't support more than 65535 tokens"

                insort_left(subtokens, tokens[token])

            self.states[ idx_states[state] ] = ArrayParseTable.StateProxy(
                tokens, idx_rules, table, len(table), len(subtokens))

            values = []
            for token_idx in subtokens:
                token = idx_tokens[token_idx]
                table.append(token_idx)

                value = productions[token]
                if value[0] is Shift:
                    values.append(idx_states[ value[1] ])
                else:
                    if value[1] not in rules:
                        rules[ value[1] ] = len(idx_rules)
                        idx_rules.append(value[1])
                        assert len(idx_rules) < 0x8000, "ArrayParseTable doesn't support more than 32767 rules"

                    ptr = rules[ value[1] ] | 0x8000
                    values.append(ptr)

            table.extend(values)


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
