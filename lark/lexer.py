## Lexer Implementation

import re

from .utils import Str, classify, get_regexp_width, Py36
from .exceptions import UnexpectedCharacters, LexError

class Pattern(object):
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
    def to_regexp(self):
        return self._get_flags(re.escape(self.value))

    @property
    def min_width(self):
        return len(self.value)
    max_width = min_width

class PatternRE(Pattern):
    def to_regexp(self):
        return self._get_flags(self.value)

    @property
    def min_width(self):
        return get_regexp_width(self.to_regexp())[0]
    @property
    def max_width(self):
        return get_regexp_width(self.to_regexp())[1]

class TerminalDef(object):
    def __init__(self, name, pattern, priority=1):
        assert isinstance(pattern, Pattern), pattern
        self.name = name
        self.pattern = pattern
        self.priority = priority

    def __repr__(self):
        return '%s(%r, %r)' % (type(self).__name__, self.name, self.pattern)



###{standalone
class Token(Str):
    __slots__ = ('type', 'pos_in_stream', 'value', 'line', 'column', 'end_line', 'end_column')

    def __new__(cls, type_, value, pos_in_stream=None, line=None, column=None, end_line=None, end_column=None):
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
        return self

    @classmethod
    def new_borrow_pos(cls, type_, value, borrow_t):
        return cls(type_, value, borrow_t.pos_in_stream, borrow_t.line, borrow_t.column, borrow_t.end_line, borrow_t.end_column)

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

        while line_ctr.char_pos < len(stream):
            lexer = self.lexer
            for mre, type_from_index in lexer.mres:
                m = mre.match(stream, line_ctr.char_pos)
                if not m:
                    continue

                t = None
                value = m.group(0)
                type_ = type_from_index[m.lastindex]
                if type_ not in ignore_types:
                    t = Token(type_, value, line_ctr.char_pos, line_ctr.line, line_ctr.column)
                    if t.type in lexer.callback:
                        t = lexer.callback[t.type](t)
                        if not isinstance(t, Token):
                            raise ValueError("Callbacks must return a token (returned %r)" % t)
                    yield t
                else:
                    if type_ in lexer.callback:
                        t = Token(type_, value, line_ctr.char_pos, line_ctr.line, line_ctr.column)
                        lexer.callback[type_](t)

                line_ctr.feed(value, type_ in newline_types)
                if t:
                    t.end_line = line_ctr.line
                    t.end_column = line_ctr.column

                break
            else:
                allowed = [v for m, tfi in lexer.mres for v in tfi.values()]
                raise UnexpectedCharacters(stream, line_ctr.char_pos, line_ctr.line, line_ctr.column, allowed=allowed, state=self.state)


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


###}



def _create_unless(terminals):
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
            m = re.match(retok.pattern.to_regexp(), s)
            if m and m.group(0) == s:
                unless.append(strtok)
                if strtok.pattern.flags <= retok.pattern.flags:
                    embedded_strs.add(strtok)
        if unless:
            callback[retok.name] = UnlessCallback(build_mres(unless, match_whole=True))

    terminals = [t for t in terminals if t not in embedded_strs]
    return terminals, callback


def _build_mres(terminals, max_size, match_whole):
    # Python sets an unreasonable group limit (currently 100) in its re module
    # Worse, the only way to know we reached it is by catching an AssertionError!
    # This function recursively tries less and less groups until it's successful.
    postfix = '$' if match_whole else ''
    mres = []
    while terminals:
        try:
            mre = re.compile(u'|'.join(u'(?P<%s>%s)'%(t.name, t.pattern.to_regexp()+postfix) for t in terminals[:max_size]))
        except AssertionError:  # Yes, this is what Python provides us.. :/
            return _build_mres(terminals, max_size//2, match_whole)

        # terms_from_name = {t.name: t for t in terminals[:max_size]}
        mres.append((mre, {i:n for n,i in mre.groupindex.items()} ))
        terminals = terminals[max_size:]
    return mres

def build_mres(terminals, match_whole=False):
    return _build_mres(terminals, len(terminals), match_whole)

def _regexp_has_newline(r):
    """Expressions that may indicate newlines in a regexp:
        - newlines (\n)
        - escaped newline (\\n)
        - anything but ([^...])
        - any-char (.) when the flag (?s) exists
    """
    return '\n' in r or '\\n' in r or '[^' in r or ('(?s' in r and '.' in r)

class Lexer:
    """Lexer interface

    Method Signatures:
        lex(self, stream) -> Iterator[Token]

        set_parser_state(self, state)   # Optional
    """
    set_parser_state = NotImplemented
    lex = NotImplemented

class TraditionalLexer(Lexer):
    def __init__(self, terminals, ignore=(), user_callbacks={}):
        assert all(isinstance(t, TerminalDef) for t in terminals), terminals

        terminals = list(terminals)

        # Sanitization
        for t in terminals:
            try:
                re.compile(t.pattern.to_regexp())
            except:
                raise LexError("Cannot compile token %s: %s" % (t.name, t.pattern))

            if t.pattern.min_width == 0:
                raise LexError("Lexer does not allow zero-width terminals. (%s: %s)" % (t.name, t.pattern))

        assert set(ignore) <= {t.name for t in terminals}

        # Init
        self.newline_types = [t.name for t in terminals if _regexp_has_newline(t.pattern.to_regexp())]
        self.ignore_types = list(ignore)

        terminals.sort(key=lambda x:(-x.priority, -x.pattern.max_width, -len(x.pattern.value), x.name))

        terminals, self.callback = _create_unless(terminals)
        assert all(self.callback.values())

        for type_, f in user_callbacks.items():
            if type_ in self.callback:
                # Already a callback there, probably UnlessCallback
                self.callback[type_] = CallChain(self.callback[type_], f, lambda t: t.type == type_)
            else:
                self.callback[type_] = f

        self.terminals = terminals

        self.mres = build_mres(terminals)


    def lex(self, stream):
        return _Lex(self).lex(stream, self.newline_types, self.ignore_types)


class ContextualLexer(Lexer):
    def __init__(self, terminals, states, ignore=(), always_accept=(), user_callbacks={}):
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
                lexer = TraditionalLexer(state_tokens, ignore=ignore, user_callbacks=user_callbacks)
                lexer_by_tokens[key] = lexer

            self.lexers[state] = lexer

        self.root_lexer = TraditionalLexer(terminals, ignore=ignore, user_callbacks=user_callbacks)

        self.set_parser_state(None) # Needs to be set on the outside

    def set_parser_state(self, state):
        self.parser_state = state

    def lex(self, stream):
        l = _Lex(self.lexers[self.parser_state], self.parser_state)
        for x in l.lex(stream, self.root_lexer.newline_types, self.root_lexer.ignore_types):
            yield x
            l.lexer = self.lexers[self.parser_state]
            l.state = self.parser_state


