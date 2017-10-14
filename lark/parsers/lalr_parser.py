"""This module implements a LALR(1) Parser
"""
# Author: Erez Shinan (2017)
# Email : erezshin@gmail.com

from ..common import ParseError, UnexpectedToken

from .lalr_analysis import LALR_Analyzer, ACTION_SHIFT

class Parser:
    def __init__(self, parser_conf):
        assert all(o is None or o.priority is None for n,x,a,o in parser_conf.rules), "LALR doesn't yet support prioritization"
        self.analysis = analysis = LALR_Analyzer(parser_conf.rules, parser_conf.start)
        analysis.compute_lookahead()
        callbacks = {rule: getattr(parser_conf.callback, rule.alias or rule.origin, None)
                          for rule in analysis.rules}

        self.parser = _Parser(analysis.states_idx, analysis.init_state_idx, analysis.start_symbol, callbacks)
        self.parse = self.parser.parse

class _Parser:
    def __init__(self, states, init_state, start_symbol, callbacks):
        self.states = states
        self.init_state = init_state
        self.start_symbol = start_symbol
        self.callbacks = callbacks

    def parse(self, seq, set_state=None):
        i = 0
        token = None
        stream = iter(seq)
        states = self.states

        state_stack = [self.init_state]
        value_stack = []

        if set_state: set_state(self.init_state)

        def get_action(key):
            state = state_stack[-1]
            try:
                return states[state][key]
            except KeyError:
                expected = states[state].keys()

                raise UnexpectedToken(token, expected, seq, i)

        def reduce(rule, size, end=False):
            if size:
                s = value_stack[-size:]
                del state_stack[-size:]
                del value_stack[-size:]
            else:
                s = []

            res = self.callbacks[rule](s)

            if end and len(state_stack) == 1 and rule.origin == self.start_symbol:
                return res

            _action, new_state = get_action(rule.origin)
            assert _action == ACTION_SHIFT
            state_stack.append(new_state)
            value_stack.append(res)

        # Main LALR-parser loop
        try:
            token = next(stream)
            i += 1
            while True:
                action, arg = get_action(token.type)

                if action == ACTION_SHIFT:
                    state_stack.append(arg)
                    value_stack.append(token)
                    if set_state: set_state(arg)
                    token = next(stream)
                    i += 1
                else:
                    reduce(*arg)
        except StopIteration:
            pass

        while True:
            _action, rule = get_action('$end')
            assert _action == 'reduce'
            res = reduce(*rule, end=True)
            if res:
                assert state_stack == [self.init_state] and not value_stack, len(state_stack)
                return res



