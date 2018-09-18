from .utils import STRING_TYPE, getLogger
log = getLogger(__name__)

###{standalone
class LarkError(Exception):
    def __eq__(self, other):
        """ Determines whether this object is equal to another one based on their hashes. """
        if isinstance(self, LarkError) is isinstance(other, LarkError):
            return str(self) == str(other)

        raise TypeError("'=' not supported between instances of '%s' and '%s'" % (
                self.__class__.__name__, other.__class__.__name__))

    def __hash__(self):
        return hash(str(self))

class GrammarError(LarkError):
    pass

class ParseError(LarkError):
    pass

class LexError(LarkError):
    pass

class SyntaxErrors(LarkError):
    def __init__(self, exceptions, messages=""):
        self.exceptions = exceptions
        if messages:
            self.messages = messages
        else:
            self.messages = '\n'.join(str(exception) for exception in exceptions)

    def __str__(self):
        return self.messages

class UnexpectedInput(LarkError):
    pos_in_stream = None

    def get_context(self, text, span=40):
        pos = self.pos_in_stream
        start = max(pos - span, 0)
        end = pos + span
        before = text[start:pos].rsplit('\n', 1)[-1]
        after = text[pos:end].split('\n', 1)[0]
        return before + after + '\n' + ' ' * len(before) + '^\n'


class UnexpectedCharacters(LexError, UnexpectedInput):
    def __init__(self, seq, lex_pos, line, column, allowed=None, considered_tokens=None, state=None):
        message = "No terminal defined for %s at line %d col %d" % (repr(seq[lex_pos]), line, column)

        self.line = line
        self.column = column
        self.allowed = allowed
        self.considered_tokens = considered_tokens
        self.pos_in_stream = lex_pos
        self.state = state

        message += '\n' + self.get_context(seq)
        if allowed:
            message += '\nExpecting: %s\n' % allowed

        super(UnexpectedCharacters, self).__init__(message)



class UnexpectedToken(ParseError, UnexpectedInput):
    def __init__(self, token, expected, considered_rules=None, state=None):
        self.token = token
        self.expected = expected     # XXX str shouldn't necessary
        self.line = getattr(token, 'line', '?')
        self.column = getattr(token, 'column', '?')
        self.considered_rules = considered_rules
        self.state = state
        self.pos_in_stream = getattr(token, 'pos_in_stream', None)

        message = ("Unexpected token %r at line %s, column %s.\n"
                   "Expected one of: \n\t* %s\n"
                   % (token, self.line, self.column, '\n\t* '.join(self.expected)))

        super(UnexpectedToken, self).__init__(message)

###}
