from .utils import STRING_TYPE, logger

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
    """UnexpectedInput Error.

    Used as a base class for the following exceptions:

    - ``UnexpectedToken``: The parser received an unexpected token
    - ``UnexpectedCharacters``: The lexer encountered an unexpected string

    After catching one of these exceptions, you may call the following helper methods to create a nicer error message.
    """
    pos_in_stream = None

    def get_context(self, text, span=40):
        """Returns a pretty string pinpointing the error in the text,
        with span amount of context characters around it.

        Note:
            The parser doesn't hold a copy of the text it has to parse,
            so you have to provide it again
        """
        pos = self.pos_in_stream
        start = max(pos - span, 0)
        end = pos + span
        if not isinstance(text, bytes):
            before = text[start:pos].rsplit('\n', 1)[-1]
            after = text[pos:end].split('\n', 1)[0]
            return before + after + '\n' + ' ' * len(before.expandtabs()) + '^\n'
        else:
            before = text[start:pos].rsplit(b'\n', 1)[-1]
            after = text[pos:end].split(b'\n', 1)[0]
            return (before + after + b'\n' + b' ' * len(before.expandtabs()) + b'^\n').decode("ascii", "backslashreplace")

    def match_examples(self, parse_fn, examples, token_type_match_fallback=False, use_accepts=False):
        """Allows you to detect what's wrong in the input text by matching
        against example errors.

        Given a parser instance and a dictionary mapping some label with
        some malformed syntax examples, it'll return the label for the
        example that bests matches the current error. The function will
        iterate the dictionary until it finds a matching error, and
        return the corresponding value.

        For an example usage, see `examples/error_reporting_lalr.py`

        Parameters:
            parse_fn: parse function (usually ``lark_instance.parse``)
            examples: dictionary of ``{'example_string': value}``.
            use_accepts: Recommended to call this with ``use_accepts=True``.
                The default is ``False`` for backwards compatibility.
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
                        if use_accepts and ut.accepts != self.accepts:
                            logger.debug("Different accepts with same state[%d]: %s != %s at example [%s][%s]" %
                                        (self.state, self.accepts, ut.accepts, i, j))
                            continue
                        try:
                            if ut.token == self.token:  # Try exact match first
                                logger.debug("Exact Match at example [%s][%s]" % (i, j))
                                return label

                            if token_type_match_fallback:
                                # Fallback to token types match
                                if (ut.token.type == self.token.type) and not candidate[-1]:
                                    logger.debug("Token Type Fallback at example [%s][%s]" % (i, j))
                                    candidate = label, True

                        except AttributeError:
                            pass
                        if not candidate[0]:
                            logger.debug("Same State match at example [%s][%s]" % (i, j))
                            candidate = label, False

        return candidate[0]


class UnexpectedCharacters(LexError, UnexpectedInput):
    def __init__(self, seq, lex_pos, line, column, allowed=None, considered_tokens=None, state=None, token_history=None):
        self.line = line
        self.column = column
        self.pos_in_stream = lex_pos
        self.state = state

        self.allowed = allowed
        self.considered_tokens = considered_tokens

        if isinstance(seq, bytes):
            _s = seq[lex_pos:lex_pos+1].decode("ascii", "backslashreplace")
        else:
            _s = seq[lex_pos]

        message = "No terminal defined for %r at line %d col %d" % (_s, line, column)
        message += '\n\n' + self.get_context(seq)
        if allowed:
            message += '\nExpecting: %s\n' % allowed
        if token_history:
            message += '\nPrevious tokens: %s\n' % ', '.join(repr(t) for t in token_history)

        super(UnexpectedCharacters, self).__init__(message)


class UnexpectedToken(ParseError, UnexpectedInput):
    """When the parser throws UnexpectedToken, it instantiates a puppet
    with its internal state. Users can then interactively set the puppet to
    the desired puppet state, and resume regular parsing.

    see: :ref:`ParserPuppet`.
    """
    def __init__(self, token, expected, considered_rules=None, state=None, puppet=None):
        self.line = getattr(token, 'line', '?')
        self.column = getattr(token, 'column', '?')
        self.pos_in_stream = getattr(token, 'pos_in_stream', None)
        self.state = state

        self.token = token
        self.expected = expected     # XXX deprecate? `accepts` is better
        self.considered_rules = considered_rules
        self.puppet = puppet

        # TODO Only calculate `accepts()` when we need to display it to the user
        # This will improve performance when doing automatic error handling
        self.accepts = puppet and puppet.accepts()

        message = ("Unexpected token %r at line %s, column %s.\n"
                   "Expected one of: \n\t* %s\n"
                   % (token, self.line, self.column, '\n\t* '.join(self.accepts or self.expected)))

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
