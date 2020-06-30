## Lexer Implementation

import re

from .utils import Str, classify, get_regexp_width, Py36, Serialize
from .exceptions import UnexpectedCharacters, LexError, UnexpectedToken

###{standalone

class Pattern(Serialize):

    def __init__(self, value, flags=()):
        self.value = value
        self.flags = frozenset(flags)

    def __repr__(self):
        return repr(self.to_regexp())

    # Pattern Hashing assumes all subclasses have a different priority!
    def __hash__(self):
        return hash((type(self), self.value, self.flags))
    def __eq__(self, other):
        return type(self) == type(other) and self.value == other.value and self.flags == other.flags

    def to_regexp(self):
        raise NotImplementedError()

    if Py36:
        # Python 3.6 changed syntax for flags in regular expression
        def _get_flags(self, value):
            for f in self.flags:
                value = ('(?%s:%s)' % (f, value))
            return value

    else:
        def _get_flags(self, value):
            for f in self.flags:
                value = ('(?%s)' % f) + value
            return value


class PatternStr(Pattern):
    __serialize_fields__ = 'value', 'flags'

    type = "str"

    def to_regexp(self):
        return self._get_flags(re.escape(self.value))

    @property
    def min_width(self):
        return len(self.value)
    max_width = min_width

class PatternRE(Pattern):
    __serialize_fields__ = 'value', 'flags', '_width'

    type = "re"

    def to_regexp(self):
        return self._get_flags(self.value)

    _width = None
    def _get_width(self):
        if self._width is None:
            self._width = get_regexp_width(self.to_regexp())
        return self._width

    @property
    def min_width(self):
        return self._get_width()[0]
    @property
    def max_width(self):
        return self._get_width()[1]


class TerminalDef(Serialize):
    __serialize_fields__ = 'name', 'pattern', 'priority'
    __serialize_namespace__ = PatternStr, PatternRE

    def __init__(self, name, pattern, priority=1):
        assert isinstance(pattern, Pattern), pattern
        self.name = name
        self.pattern = pattern
        self.priority = priority

    def __repr__(self):
        return '%s(%r, %r)' % (type(self).__name__, self.name, self.pattern)



class Token(Str):
    __slots__ = ('type', 'pos_in_stream', 'value', 'line', 'column', 'end_line', 'end_column', 'end_pos')

    def __new__(cls, type_, value, pos_in_stream=None, line=None, column=None, end_line=None, end_column=None, end_pos=None):
        try:
            self = super(Token, cls).__new__(cls, value)
        except UnicodeDecodeError:
            value = value.decode('latin1')
            self = super(Token, cls).__new__(cls, value)

        self.type = type_
        self.pos_in_stream = pos_in_stream
        self.value = value
        self.line = line
        self.column = column
        self.end_line = end_line
        self.end_column = end_column
        self.end_pos = end_pos
        return self

    def update(self, type_=None, value=None):
        return Token.new_borrow_pos(
            type_ if type_ is not None else self.type,
            value if value is not None else self.value,
            self
        )

    @classmethod
    def new_borrow_pos(cls, type_, value, borrow_t):
        return cls(type_, value, borrow_t.pos_in_stream, borrow_t.line, borrow_t.column, borrow_t.end_line, borrow_t.end_column, borrow_t.end_pos)

    def __reduce__(self):
        return (self.__class__, (self.type, self.value, self.pos_in_stream, self.line, self.column, ))

    def __repr__(self):
        return 'Token(%s, %r)' % (self.type, self.value)

    def __deepcopy__(self, memo):
        return Token(self.type, self.value, self.pos_in_stream, self.line, self.column)

    def __eq__(self, other):
        if isinstance(other, Token) and self.type != other.type:
            return False

        return Str.__eq__(self, other)

    __hash__ = Str.__hash__


class LineCounter:
    def __init__(self):
        self.newline_char = '\n'
        self.char_pos = 0
        self.line = 1
        self.column = 1
        self.line_start_pos = 0

    def feed(self, token, test_newline=True):
        """Consume a token and calculate the new line & column.

        As an optional optimization, set test_newline=False is token doesn't contain a newline.
        """
        if test_newline:
            newlines = token.count(self.newline_char)
            if newlines:
                self.line += newlines
                self.line_start_pos = self.char_pos + token.rindex(self.newline_char) + 1

        self.char_pos += len(token)
        self.column = self.char_pos - self.line_start_pos + 1

class _Lex:
    "Built to serve both Lexer and ContextualLexer"
    def __init__(self, lexer, state=None):
        self.lexer = lexer
        self.state = state

    def lex(self, stream, newline_types, ignore_types):
        newline_types = frozenset(newline_types)
        ignore_types = frozenset(ignore_types)
        line_ctr = LineCounter()
        last_token = None

        while line_ctr.char_pos < len(stream):
            lexer = self.lexer
            res = lexer.match(stream, line_ctr.char_pos)
            if not res:
                allowed = {v for m, tfi in lexer.mres for v in tfi.values()} - ignore_types
                if not allowed:
                    allowed = {"<END-OF-FILE>"}
                raise UnexpectedCharacters(stream, line_ctr.char_pos, line_ctr.line, line_ctr.column, allowed=allowed, state=self.state, token_history=last_token and [last_token])

            value, type_ = res

            if type_ not in ignore_types:
                t = Token(type_, value, line_ctr.char_pos, line_ctr.line, line_ctr.column)
                line_ctr.feed(value, type_ in newline_types)
                t.end_line = line_ctr.line
                t.end_column = line_ctr.column
                t.end_pos = line_ctr.char_pos
                if t.type in lexer.callback:
                    t = lexer.callback[t.type](t)
                    if not isinstance(t, Token):
                        raise ValueError("Callbacks must return a token (returned %r)" % t)
                yield t
                last_token = t
            else:
                if type_ in lexer.callback:
                    t2 = Token(type_, value, line_ctr.char_pos, line_ctr.line, line_ctr.column)
                    lexer.callback[type_](t2)
                line_ctr.feed(value, type_ in newline_types)




class UnlessCallback:
    def __init__(self, mres):
        self.mres = mres

    def __call__(self, t):
        for mre, type_from_index in self.mres:
            m = mre.match(t.value)
            if m:
                t.type = type_from_index[m.lastindex]
                break
        return t

class CallChain:
    def __init__(self, callback1, callback2, cond):
        self.callback1 = callback1
        self.callback2 = callback2
        self.cond = cond

    def __call__(self, t):
        t2 = self.callback1(t)
        return self.callback2(t) if self.cond(t2) else t2





def _create_unless(terminals, g_regex_flags, re_):
    tokens_by_type = classify(terminals, lambda t: type(t.pattern))
    assert len(tokens_by_type) <= 2, tokens_by_type.keys()
    embedded_strs = set()
    callback = {}
    for retok in tokens_by_type.get(PatternRE, []):
        unless = [] # {}
        for strtok in tokens_by_type.get(PatternStr, []):
            if strtok.priority > retok.priority:
                continue
            s = strtok.pattern.value
            m = re_.match(retok.pattern.to_regexp(), s, g_regex_flags)
            if m and m.group(0) == s:
                unless.append(strtok)
                if strtok.pattern.flags <= retok.pattern.flags:
                    embedded_strs.add(strtok)
        if unless:
            callback[retok.name] = UnlessCallback(build_mres(unless, g_regex_flags, re_, match_whole=True))

    terminals = [t for t in terminals if t not in embedded_strs]
    return terminals, callback


def _build_mres(terminals, max_size, g_regex_flags, match_whole, re_):
    # Python sets an unreasonable group limit (currently 100) in its re module
    # Worse, the only way to know we reached it is by catching an AssertionError!
    # This function recursively tries less and less groups until it's successful.
    postfix = '$' if match_whole else ''
    mres = []
    while terminals:
        try:
            mre = re_.compile(u'|'.join(u'(?P<%s>%s)'%(t.name, t.pattern.to_regexp()+postfix) for t in terminals[:max_size]), g_regex_flags)
        except AssertionError:  # Yes, this is what Python provides us.. :/
            return _build_mres(terminals, max_size//2, g_regex_flags, match_whole, re_)

        # terms_from_name = {t.name: t for t in terminals[:max_size]}
        mres.append((mre, {i:n for n,i in mre.groupindex.items()} ))
        terminals = terminals[max_size:]
    return mres

def build_mres(terminals, g_regex_flags, re_, match_whole=False):
    return _build_mres(terminals, len(terminals), g_regex_flags, match_whole, re_)

def _regexp_has_newline(r):
    r"""Expressions that may indicate newlines in a regexp:
        - newlines (\n)
        - escaped newline (\\n)
        - anything but ([^...])
        - any-char (.) when the flag (?s) exists
        - spaces (\s)
    """
    return '\n' in r or '\\n' in r or '\\s' in r or '[^' in r or ('(?s' in r and '.' in r)

class Lexer(object):
    """Lexer interface

    Method Signatures:
        lex(self, stream) -> Iterator[Token]
    """
    lex = NotImplemented


class TraditionalLexer(Lexer):

    def __init__(self, terminals, re_, ignore=(), user_callbacks={}, g_regex_flags=0):
        assert all(isinstance(t, TerminalDef) for t in terminals), terminals

        terminals = list(terminals)

        self.re = re_
        # Sanitization
        for t in terminals:
            try:
                self.re.compile(t.pattern.to_regexp(), g_regex_flags)
            except self.re.error:
                raise LexError("Cannot compile token %s: %s" % (t.name, t.pattern))

            if t.pattern.min_width == 0:
                raise LexError("Lexer does not allow zero-width terminals. (%s: %s)" % (t.name, t.pattern))

        assert set(ignore) <= {t.name for t in terminals}

        # Init
        self.newline_types = [t.name for t in terminals if _regexp_has_newline(t.pattern.to_regexp())]
        self.ignore_types = list(ignore)

        terminals.sort(key=lambda x:(-x.priority, -x.pattern.max_width, -len(x.pattern.value), x.name))
        self.terminals = terminals
        self.user_callbacks = user_callbacks
        self.build(g_regex_flags)

    def build(self, g_regex_flags=0):
        terminals, self.callback = _create_unless(self.terminals, g_regex_flags, re_=self.re)
        assert all(self.callback.values())

        for type_, f in self.user_callbacks.items():
            if type_ in self.callback:
                # Already a callback there, probably UnlessCallback
                self.callback[type_] = CallChain(self.callback[type_], f, lambda t: t.type == type_)
            else:
                self.callback[type_] = f

        self.mres = build_mres(terminals, g_regex_flags, self.re)

    def match(self, stream, pos):
        for mre, type_from_index in self.mres:
            m = mre.match(stream, pos)
            if m:
                return m.group(0), type_from_index[m.lastindex]

    def lex(self, stream):
        return _Lex(self).lex(stream, self.newline_types, self.ignore_types)




class ContextualLexer(Lexer):

    def __init__(self, terminals, states, re_, ignore=(), always_accept=(), user_callbacks={}, g_regex_flags=0):
        self.re = re_
        tokens_by_name = {}
        for t in terminals:
            assert t.name not in tokens_by_name, t
            tokens_by_name[t.name] = t

        lexer_by_tokens = {}
        self.lexers = {}
        for state, accepts in states.items():
            key = frozenset(accepts)
            try:
                lexer = lexer_by_tokens[key]
            except KeyError:
                accepts = set(accepts) | set(ignore) | set(always_accept)
                state_tokens = [tokens_by_name[n] for n in accepts if n and n in tokens_by_name]
                lexer = TraditionalLexer(state_tokens, re_=self.re, ignore=ignore, user_callbacks=user_callbacks, g_regex_flags=g_regex_flags)
                lexer_by_tokens[key] = lexer

            self.lexers[state] = lexer

        self.root_lexer = TraditionalLexer(terminals, re_=self.re, ignore=ignore, user_callbacks=user_callbacks, g_regex_flags=g_regex_flags)

    def lex(self, stream, get_parser_state):
        parser_state = get_parser_state()
        l = _Lex(self.lexers[parser_state], parser_state)
        try:
            for x in l.lex(stream, self.root_lexer.newline_types, self.root_lexer.ignore_types):
                yield x
                parser_state = get_parser_state()
                l.lexer = self.lexers[parser_state]
                l.state = parser_state # For debug only, no need to worry about multithreading
        except UnexpectedCharacters as e:
            # In the contextual lexer, UnexpectedCharacters can mean that the terminal is defined,
            # but not in the current context.
            # This tests the input against the global context, to provide a nicer error.
            root_match = self.root_lexer.match(stream, e.pos_in_stream)
            if not root_match:
                raise

            value, type_ = root_match
            t = Token(type_, value, e.pos_in_stream, e.line, e.column)
            raise UnexpectedToken(t, e.allowed, state=e.state)

###}
