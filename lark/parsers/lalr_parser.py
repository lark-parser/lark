from .lalr_analysis import ACTION_SHIFT
from ..common import ParseError, UnexpectedToken


class Parser(object):
    def __init__(self, analysis, callback):
        self.analysis = analysis
        self.callbacks = {rule: getattr(callback, rule.alias or rule.origin, None)
                          for rule in analysis.rules}

    def parse(self, seq):
        states_idx = self.analysis.states_idx

        state_stack = [self.analysis.init_state_idx]
        value_stack = []
        i = 0

        def get_action(key):
            state = state_stack[-1]
            try:
                return states_idx[state][key]
            except KeyError:
                expected = states_idx[state].keys()
                try:
                    token = seq[i]
                except IndexError:
                    assert key == '$end'
                    token = seq[-1]

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
        while i < len(seq):
            action, arg = get_action(seq[i].type)

            if action == ACTION_SHIFT:
                state_stack.append(arg)
                value_stack.append(seq[i])
                i+= 1
            else:
                reduce(*arg)

        while True:
            _action, rule = get_action('$end')
            assert _action == 'reduce'
            res = reduce(*rule)
            if res:
                assert state_stack == [self.analysis.init_state_idx] and not value_stack, len(state_stack)
                return res



