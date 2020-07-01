# This module provide a LALR puppet, which is used to debugging and error handling

from copy import deepcopy

from .lalr_analysis import Shift, Reduce

class ParserPuppet:
    def __init__(self, parser, state_stack, value_stack, start, stream, set_state):
        self.parser = parser
        self._state_stack = state_stack
        self._value_stack = value_stack
        self._start = start
        self._stream = stream
        self._set_state = set_state

        self.result = None

    def feed_token(self, token):
        """Advance the parser state, as if it just recieved `token` from the lexer

        """
        end_state = self.parser.parse_table.end_states[self._start]
        state_stack = self._state_stack
        value_stack = self._value_stack

        state = state_stack[-1]
        action, arg = self.parser.parse_table.states[state][token.type]
        assert arg != end_state

        while action is Reduce:
            rule = arg
            size = len(rule.expansion)
            if size:
                s = value_stack[-size:]
                del state_stack[-size:]
                del value_stack[-size:]
            else:
                s = []

            value = self.parser.callbacks[rule](s)

            _action, new_state = self.parser.parse_table.states[state_stack[-1]][rule.origin.name]
            assert _action is Shift
            state_stack.append(new_state)
            value_stack.append(value)

            if state_stack[-1] == end_state:
                self.result = value_stack[-1]
                return self.result

            state = state_stack[-1]
            action, arg = self.parser.parse_table.states[state][token.type]
            assert arg != end_state

        assert action is Shift
        state_stack.append(arg)
        value_stack.append(token)

    def copy(self):
        return type(self)(
            self.parser,
            list(self._state_stack),
            deepcopy(self._value_stack),
            self._start,
            self._stream,
            self._set_state,
        )

    def pretty():
        print("Puppet choices:")
        for k, v in self.choices.items():
            print('\t-', k, '->', v)
        print('stack size:', len(self._state_stack))

    def choices(self):
        return self.parser.parse_table.states[self._state_stack[-1]]

    def resume_parse(self):
        return self.parser.parse(self._stream, self._start, self._set_state, self._value_stack, self._state_stack)
