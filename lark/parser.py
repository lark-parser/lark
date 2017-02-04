from grammar_analysis import ACTION_SHIFT

class ParseError(Exception):
    pass

class Parser(object):
    def __init__(self, ga, callback, temp=False):
        self.ga = ga
        self.callbacks = {rule: getattr(callback, rule.alias or rule.origin, None)
                          for rule in ga.rules}

    def parse(self, seq):
        states_idx = self.ga.states_idx

        stack = [(None, self.ga.init_state_idx)]
        i = 0
        res = None

        def get_action(key):
            state = stack[-1][1]
            try:
                return states_idx[state][key]
            except KeyError:
                expected = states_idx[state].keys()
                context = ' '.join(['%s(%r)' % (t.type, t.value) for t in seq[i:i+5]])
                raise ParseError("Unexpected input %r.\nExpected: %s\nContext: %s" % (key, expected, context))

        def reduce(rule):
            s = stack[-len(rule.expansion):]
            del stack[-len(rule.expansion):]

            res = self.callbacks[rule]([x[0] for x in s])

            if rule.origin == 'start':
                return res

            _action, new_state = get_action(rule.origin)
            assert _action == ACTION_SHIFT
            stack.append((res, new_state))

        # Main LALR-parser loop
        while i < len(seq):
            action, arg = get_action(seq[i].type)

            if action == ACTION_SHIFT:
                stack.append((seq[i], arg))
                i+= 1
            else:
                reduce(arg)

        while len(stack) > 1:
            _action, rule = get_action('$end')
            assert _action == 'reduce'
            res = reduce(rule)
            if res:
                break

        assert stack == [(None, self.ga.init_state_idx)], len(stack)
        return res


