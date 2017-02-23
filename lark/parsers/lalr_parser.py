"""This module implements a LALR(1) Parser
"""
# Author: Erez Shinan (2017)
# Email : erezshin@gmail.com

from ..common import ParseError, UnexpectedToken

from .lalr_analysis import LALR_Analyzer, ACTION_SHIFT

class Parser(object):
    def __init__(self, parser_conf):
        self.analysis = LALR_Analyzer(parser_conf.rules, parser_conf.start)
        self.analysis.compute_lookahead()
        self.callbacks = {rule: getattr(parser_conf.callback, rule.alias or rule.origin, None)
                          for rule in self.analysis.rules}

    def parse(self, seq, set_state=None):
        i = 0
        token = None
        stream = iter(seq)
        states_idx = self.analysis.states_idx

        state_stack = [self.analysis.init_state_idx]
        value_stack = []

        if set_state: set_state(self.analysis.init_state_idx)

        def get_action(key):
            state = state_stack[-1]
            try:
                return states_idx[state][key]
            except KeyError:
                expected = states_idx[state].keys()

                raise UnexpectedToken(token, expected, seq, i)

        def reduce(rule, size):
            if size:
                s = value_stack[-size:]
                del state_stack[-size:]
                del value_stack[-size:]
            else:
                s = []

            res = self.callbacks[rule](s)

            if len(state_stack) == 1 and rule.origin == self.analysis.start_symbol:
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
            res = reduce(*rule)
            if res:
                assert state_stack == [self.analysis.init_state_idx] and not value_stack, len(state_stack)
                return res



