# This module provide a LALR puppet, which is used to debugging and error handling

from copy import copy

from .lalr_analysis import Shift, Reduce
from .. import Token
from ..exceptions import UnexpectedToken


class ParserPuppet(object):
    """ParserPuppet gives you advanced control over error handling when parsing with LALR.

    For a simpler, more streamlined interface, see the ``on_error`` argument to ``Lark.parse()``.
    """
    def __init__(self, parser, parser_state, lexer_state):
        self.parser = parser
        self.parser_state = parser_state
        self.lexer_state = lexer_state

    def feed_token(self, token):
        """Feed the parser with a token, and advance it to the next state, as if it received it from the lexer.

        Note that ``token`` has to be an instance of ``Token``.
        """
        return self.parser_state.feed_token(token, token.type == '$END')

    def __copy__(self):
        """Create a new puppet with a separate state.

        Calls to feed_token() won't affect the old puppet, and vice-versa.
        """
        return type(self)(
            self.parser,
            copy(self.parser_state),
            copy(self.lexer_state),
        )

    def copy(self):
        return copy(self)

    def __eq__(self, other):
        if not isinstance(other, ParserPuppet):
            return False

        return self.parser_state == other.parser_state and self.lexer_state == other.lexer_state

    def as_immutable(self):
        p = copy(self)
        return ImmutableParserPuppet(p.parser, p.parser_state, p.lexer_state)

    def pretty(self):
        """Print the output of ``choices()`` in a way that's easier to read."""
        out = ["Puppet choices:"]
        for k, v in self.choices().items():
            out.append('\t- %s -> %s' % (k, v))
        out.append('stack size: %s' % len(self.parser_state.state_stack))
        return '\n'.join(out)

    def choices(self):
        """Returns a dictionary of token types, matched to their action in the parser.

        Only returns token types that are accepted by the current state.

        Updated by ``feed_token()``.
        """
        return self.parser_state.parse_conf.parse_table.states[self.parser_state.position]

    def accepts(self):
        accepts = set()
        for t in self.choices():
            if t.isupper(): # is terminal?
                new_puppet = copy(self)
                try:
                    new_puppet.feed_token(Token(t, ''))
                except UnexpectedToken:
                    pass
                else:
                    accepts.add(t)
        return accepts

    def resume_parse(self):
        """Resume parsing from the current puppet state."""
        return self.parser.parse_from_state(self.parser_state)



class ImmutableParserPuppet(ParserPuppet):
    result = None

    def __hash__(self):
        return hash((self.parser_state, self.lexer_state))

    def feed_token(self, token):
        c = copy(self)
        c.result = ParserPuppet.feed_token(c, token)
        return c