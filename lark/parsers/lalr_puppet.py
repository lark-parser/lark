# This module provide a LALR puppet, which is used to debugging and error handling

from copy import deepcopy

from .lalr_analysis import Shift, Reduce
from .. import Token
from ..exceptions import ParseError


class ParserPuppet(object):
    """ParserPuppet gives you advanced control over error handling when parsing with LALR.

    For a simpler, more streamlined interface, see the ``on_error`` argument to ``Lark.parse()``.
    """
    def __init__(self, parser, state_stack, value_stack, start, stream, set_state):
        self.parser = parser
        self._state_stack = state_stack
        self._value_stack = value_stack
        self._start = start
        self._stream = stream
        self._set_state = set_state

        self.result = None

    def feed_token(self, token):
        """Feed the parser with a token, and advance it to the next state, as if it recieved it from the lexer.

        Note that ``token`` has to be an instance of ``Token``.
        """
        end_state = self.parser.parse_table.end_states[self._start]
        state_stack = self._state_stack
        value_stack = self._value_stack

        state = state_stack[-1]
        action, arg = self.parser.parse_table.states[state][token.type]
        if arg == end_state:
            raise ParseError(arg)

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
            try:
                action, arg = self.parser.parse_table.states[state][token.type]
            except KeyError as e:
                raise ParseError(e)
            assert arg != end_state

        assert action is Shift
        state_stack.append(arg)
        value_stack.append(token)

    def copy(self):
        """Create a new puppet with a separate state.

        Calls to feed_token() won't affect the old puppet, and vice-versa.
        """
        return type(self)(
            self.parser,
            list(self._state_stack),
            deepcopy(self._value_stack),
            self._start,
            self._stream,
            self._set_state,
        )

    def __eq__(self, other):
        if not isinstance(other, ParserPuppet):
            return False

        return (
            self._state_stack == other._state_stack and
            self._value_stack == other._value_stack and
            self._stream == other._stream and
            self._start == other._start
        )

    def __hash__(self):
        return hash((tuple(self._state_stack), self._start))

    def pretty(self):
        """Print the output of ``choices()`` in a way that's easier to read."""
        out = ["Puppet choices:"]
        for k, v in self.choices().items():
            out.append('\t- %s -> %s' % (k, v))
        out.append('stack size: %s' % len(self._state_stack))
        return '\n'.join(out)

    def choices(self):
        """Returns a dictionary of token types, matched to their action in the parser.

        Only returns token types that are accepted by the current state.

        Updated by ``feed_token()``.
        """
        return self.parser.parse_table.states[self._state_stack[-1]]

    def accepts(self):
        accepts = set()
        for t in self.choices():
            if t.isupper(): # is terminal?
                new_puppet = self.copy()
                try:
                    new_puppet.feed_token(Token(t, ''))
                except ParseError:
                    pass
                else:
                    accepts.add(t)
        return accepts

    def resume_parse(self):
        """Resume parsing from the current puppet state."""
        return self.parser.parse(
            self._stream, self._start, self._set_state,
            self._value_stack, self._state_stack
        )
