from .utils import STRING_TYPE

###{standalone
class LarkError(Exception):
    pass

class GrammarError(LarkError):
    pass

class ParseError(LarkError):
    pass

class LexError(LarkError):
    pass

class UnexpectedEOF(ParseError):
    def __init__(self, expected):
        self.expected = expected

        message = ("Unexpected end-of-input. Expected one of: \n\t* %s\n" % '\n\t* '.join(x.name for x in self.expected))
        super(UnexpectedEOF, self).__init__(message)


class UnexpectedInput(LarkError):
    pos_in_stream = None

    def get_context(self, text, span=40):
        pos = self.pos_in_stream
        start = max(pos - span, 0)
        end = pos + span
        if not isinstance(text, bytes):
            before = text[start:pos].rsplit('\n', 1)[-1]
            after = text[pos:end].split('\n', 1)[0]
            return before + after + '\n' + ' ' * len(before) + '^\n'
        else:
            before = text[start:pos].rsplit(b'\n', 1)[-1]
            after = text[pos:end].split(b'\n', 1)[0]
            return (before + after + b'\n' + b' ' * len(before) + b'^\n').decode("ascii", "backslashreplace")

    def match_examples(self, parse_fn, examples, token_type_match_fallback=False, print_debug_info=True):
        """ Given a parser instance and a dictionary mapping some label with
            some malformed syntax examples, it'll return the label for the
            example that bests matches the current error.
        """
        assert self.state is not None, "Not supported for this exception"
        
        if isinstance(examples, dict):
            examples = examples.items()

        candidate = (None, False)
        for i, (label, example) in enumerate(examples):
            assert not isinstance(example, STRING_TYPE)

            for j, malformed in enumerate(example):
                try:
                    parse_fn(malformed)
                except UnexpectedInput as ut:
                    if ut.state == self.state:
                        try:
                            if ut.token == self.token:  # Try exact match first
                                if print_debug_info:
                                    print("Exact Match at %d, with example %d" % (i, j), (ut.token, self.token, ut.state, self.state))
                                return label

                            if token_type_match_fallback:
                                # Fallback to token types match
                                if (ut.token.type == self.token.type) and not candidate[-1]:
                                    if print_debug_info:
                                        print("Token Type Fallback at %d, with example %d" % (i, j))
                                    candidate = label, True

                        except AttributeError:
                            pass
                        if not candidate[0]:
                            if print_debug_info:
                                print("Defaulted at %d, with example %d" % (i, j))
                            candidate = label, False

        return candidate[0]


class UnexpectedCharacters(LexError, UnexpectedInput):
    def __init__(self, seq, lex_pos, line, column, allowed=None, considered_tokens=None, state=None, token_history=None):
        
        if isinstance(seq, bytes):
            message = "No terminal defined for '%s' at line %d col %d" % (seq[lex_pos:lex_pos+1].decode("ascii", "backslashreplace"), line, column)
        else:
            message = "No terminal defined for '%s' at line %d col %d" % (seq[lex_pos], line, column)

        self.line = line
        self.column = column
        self.allowed = allowed
        self.considered_tokens = considered_tokens
        self.pos_in_stream = lex_pos
        self.state = state

        message += '\n\n' + self.get_context(seq)
        if allowed:
            message += '\nExpecting: %s\n' % allowed
        if token_history:
            message += '\nPrevious tokens: %s\n' % ', '.join(repr(t) for t in token_history)

        super(UnexpectedCharacters, self).__init__(message)



class UnexpectedToken(ParseError, UnexpectedInput):
    def __init__(self, token, expected, considered_rules=None, state=None, puppet=None):
        self.token = token
        self.expected = expected     # XXX str shouldn't necessary
        self.line = getattr(token, 'line', '?')
        self.column = getattr(token, 'column', '?')
        self.considered_rules = considered_rules
        self.state = state
        self.pos_in_stream = getattr(token, 'pos_in_stream', None)
        self.puppet = puppet

        message = ("Unexpected token %r at line %s, column %s.\n"
                   "Expected one of: \n\t* %s\n"
                   % (token, self.line, self.column, '\n\t* '.join(self.expected)))

        super(UnexpectedToken, self).__init__(message)

class VisitError(LarkError):
    """VisitError is raised when visitors are interrupted by an exception

    It provides the following attributes for inspection:
    - obj: the tree node or token it was processing when the exception was raised
    - orig_exc: the exception that cause it to fail
    """
    def __init__(self, rule, obj, orig_exc):
        self.obj = obj
        self.orig_exc = orig_exc

        message = 'Error trying to process rule "%s":\n\n%s' % (rule, orig_exc)
        super(VisitError, self).__init__(message)
###}
