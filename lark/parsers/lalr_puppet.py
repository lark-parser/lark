# This module provides a LALR interactive parser, which is used for debugging and error handling

from copy import copy

from .. import Token
from ..exceptions import UnexpectedToken


class InteractiveParser(object):
    """InteractiveParser gives you advanced control over parsing and error handling when parsing with LALR.

    For a simpler interface, see the ``on_error`` argument to ``Lark.parse()``.
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
    
    def exhaust_lexer(self):
        """Try to feed the rest of the lexer state into the interactive parser.
        
        Note that this modifies the instance in place and does not feed an '$END' Token"""
        for token in self.lexer_state.lex(self.parser_state):
            self.parser_state.feed_token(token)
    
    def feed_eof(self, last_token=None):
        """Feed a '$END' Token. Borrows from 'last_token' if given."""
        eof = Token.new_borrow_pos('$END', '', last_token) if last_token is not None else Token('$END', '', 0, 1, 1)
        return self.feed_token(eof)


    def __copy__(self):
        """Create a new interactive parser with a separate state.

        Calls to feed_token() won't affect the old instance, and vice-versa.
        """
        return type(self)(
            self.parser,
            copy(self.parser_state),
            copy(self.lexer_state),
        )

    def copy(self):
        return copy(self)

    def __eq__(self, other):
        if not isinstance(other, InteractiveParser):
            return False

        return self.parser_state == other.parser_state and self.lexer_state == other.lexer_state

    def as_immutable(self):
        """Convert to an ``ImmutableInteractiveParser``."""
        p = copy(self)
        return ImmutableInteractiveParser(p.parser, p.parser_state, p.lexer_state)

    def pretty(self):
        """Print the output of ``choices()`` in a way that's easier to read."""
        out = ["Parser choices:"]
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
        """Returns the set of possible tokens that will advance the parser into a new valid state."""
        accepts = set()
        for t in self.choices():
            if t.isupper(): # is terminal?
                new_cursor = copy(self)
                try:
                    new_cursor.feed_token(Token(t, ''))
                except UnexpectedToken:
                    pass
                else:
                    accepts.add(t)
        return accepts

    def resume_parse(self):
        """Resume automated parsing from the current state."""
        return self.parser.parse_from_state(self.parser_state)



class ImmutableInteractiveParser(InteractiveParser):
    """Same as ``InteractiveParser``, but operations create a new instance instead
    of changing it in-place.
    """

    result = None

    def __hash__(self):
        return hash((self.parser_state, self.lexer_state))

    def feed_token(self, token):
        c = copy(self)
        c.result = InteractiveParser.feed_token(c, token)
        return c

    def exhaust_lexer(self):
        """Try to feed the rest of the lexer state into the parser.

        Note that this returns a new ImmutableInteractiveParser and does not feed an '$END' Token"""
        cursor = self.as_mutable()
        cursor.exhaust_lexer()
        return cursor.as_immutable()

    def as_mutable(self):
        """Convert to an ``InteractiveParser``."""
        p = copy(self)
        return InteractiveParser(p.parser, p.parser_state, p.lexer_state)


# Deprecated class names for the interactive parser
ParserPuppet = InteractiveParser
ImmutableParserPuppet = ImmutableInteractiveParser
