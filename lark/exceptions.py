from warnings import warn

from .utils import STRING_TYPE, logger, NO_VALUE


###{standalone


class LarkError(Exception):
    pass


class ConfigurationError(LarkError, ValueError):
    pass


def assert_config(value, options, msg='Got %r, expected one of %s'):
    if value not in options:
        raise ConfigurationError(msg % (value, options))


class GrammarError(LarkError):
    pass


class ParseError(LarkError):
    pass


class LexError(LarkError):
    pass


class UnexpectedInput(LarkError):
    """UnexpectedInput Error.

    Used as a base class for the following exceptions:

    - ``UnexpectedToken``: The parser received an unexpected token
    - ``UnexpectedCharacters``: The lexer encountered an unexpected string

    After catching one of these exceptions, you may call the following helper methods to create a nicer error message.
    """
    pos_in_stream = None
    _terminals_by_name = None

    def get_context(self, text, span=40):
        """Returns a pretty string pinpointing the error in the text,
        with span amount of context characters around it.

        Note:
            The parser doesn't hold a copy of the text it has to parse,
            so you have to provide it again
        """
        assert self.pos_in_stream is not None, self
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
                        if use_accepts and hasattr(self, 'accepts') and ut.accepts != self.accepts:
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
                        if candidate[0] is None:
                            logger.debug("Same State match at example [%s][%s]" % (i, j))
                            candidate = label, False

        return candidate[0]

    def _format_expected(self, expected):
        if self._terminals_by_name:
            d = self._terminals_by_name
            expected = [d[t_name].user_repr() if t_name in d else t_name for t_name in expected]
        return "Expected one of: \n\t* %s\n" % '\n\t* '.join(expected)


class UnexpectedEOF(ParseError, UnexpectedInput):
    def __init__(self, expected, state=None, terminals_by_name=None):
        self.expected = expected
        self.state = state
        from .lexer import Token
        self.token = Token("<EOF>", "")  # , line=-1, column=-1, pos_in_stream=-1)
        self.pos_in_stream = -1
        self.line = -1
        self.column = -1
        self._terminals_by_name = terminals_by_name

        super(UnexpectedEOF, self).__init__()

    def __str__(self):
        message = "Unexpected end-of-input. "
        message += self._format_expected(self.expected)
        return message


class UnexpectedCharacters(LexError, UnexpectedInput):
    def __init__(self, seq, lex_pos, line, column, allowed=None, considered_tokens=None, state=None, token_history=None,
                 terminals_by_name=None, considered_rules=None):
        # TODO considered_tokens and allowed can be figured out using state
        self.line = line
        self.column = column
        self.pos_in_stream = lex_pos
        self.state = state
        self._terminals_by_name = terminals_by_name

        self.allowed = allowed
        self.considered_tokens = considered_tokens
        self.considered_rules = considered_rules
        self.token_history = token_history

        if isinstance(seq, bytes):
            self.char = seq[lex_pos:lex_pos + 1].decode("ascii", "backslashreplace")
        else:
            self.char = seq[lex_pos]
        self._context = self.get_context(seq)

        super(UnexpectedCharacters, self).__init__()

    def __str__(self):
        message = "No terminal matches '%s' in the current parser context, at line %d col %d" % (self.char, self.line, self.column)
        message += '\n\n' + self._context
        if self.allowed:
            message += self._format_expected(self.allowed)
        if self.token_history:
            message += '\nPrevious tokens: %s\n' % ', '.join(repr(t) for t in self.token_history)
        return message


class UnexpectedToken(ParseError, UnexpectedInput):
    """An exception that is raised by the parser, when the token it received
    doesn't match any valid step forward.

    The parser provides an interactive instance through `interactive_parser`,
    which is initialized to the point of failture, and can be used for debugging and error handling.

    see: ``InteractiveParser``.
    """

    def __init__(self, token, expected, considered_rules=None, state=None, interactive_parser=None, terminals_by_name=None, token_history=None):
        # TODO considered_rules and expected can be figured out using state
        self.line = getattr(token, 'line', '?')
        self.column = getattr(token, 'column', '?')
        self.pos_in_stream = getattr(token, 'pos_in_stream', None)
        self.state = state

        self.token = token
        self.expected = expected  # XXX deprecate? `accepts` is better
        self._accepts = NO_VALUE
        self.considered_rules = considered_rules
        self.interactive_parser = interactive_parser
        self._terminals_by_name = terminals_by_name
        self.token_history = token_history

        super(UnexpectedToken, self).__init__()

    @property
    def accepts(self):
        if self._accepts is NO_VALUE:
            self._accepts = self.interactive_parser and self.interactive_parser.accepts()
        return self._accepts

    def __str__(self):
        message = ("Unexpected token %r at line %s, column %s.\n%s"
                   % (self.token, self.line, self.column, self._format_expected(self.accepts or self.expected)))
        if self.token_history:
            message += "Previous tokens: %r\n" % self.token_history

        return message

    @property
    def puppet(self):
        warn("UnexpectedToken.puppet attribute has been renamed to interactive_parser", DeprecationWarning)
        return self.interactive_parser
    


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
