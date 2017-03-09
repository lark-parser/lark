import re

class GrammarError(Exception):
    pass

class ParseError(Exception):
    pass


class UnexpectedToken(ParseError):
    def __init__(self, token, expected, seq, index):
        self.token = token
        self.expected = expected
        self.line = getattr(token, 'line', '?')
        self.column = getattr(token, 'column', '?')

        try:
            context = ' '.join(['%r(%s)' % (t.value, t.type) for t in seq[index:index+5]])
        except AttributeError:
            context = seq[index:index+5]
        except TypeError:
            context = "<no context>"
        message = ("Unexpected token %r at line %s, column %s.\n"
                   "Expected: %s\n"
                   "Context: %s" % (token, self.line, self.column, expected, context))

        super(UnexpectedToken, self).__init__(message)



def is_terminal(sym):
    return isinstance(sym, Terminal) or sym.isupper() or sym[0] == '$'


class LexerConf:
    def __init__(self, tokens, ignore, postlex):
        self.tokens = tokens
        self.ignore = ignore
        self.postlex = postlex

class ParserConf:
    def __init__(self, rules, callback, start):
        assert all(len(r)==3 for r in rules)
        self.rules = rules
        self.callback = callback
        self.start = start



class Pattern(object):
    def __init__(self, value, flags=None):
        self.value = value
        self.flags = flags

    def __repr__(self):
        return repr(self._get_flags() + self.value)

    # Pattern Hashing assumes all subclasses have a different priority!
    def __hash__(self):
        return hash((self.priority, self.value))
    def __eq__(self, other):
        return self.priority == other.priority and self.value == other.value

    def _get_flags(self):
        if self.flags:
            assert len(self.flags) == 1
            return '(?%s)' % self.flags
        return ''

class PatternStr(Pattern):
    def to_regexp(self):
        return self._get_flags() + re.escape(self.value)

    priority = 0

class PatternRE(Pattern):
    def to_regexp(self):
        return self._get_flags() + self.value

    priority = 1

class TokenDef(object):
    def __init__(self, name, pattern):
        assert isinstance(pattern, Pattern), pattern
        self.name = name
        self.pattern = pattern

    def __repr__(self):
        return '%s(%r, %r)' % (type(self).__name__, self.name, self.pattern)


class Terminal:
    def __init__(self, data):
        self.data = data

    def __repr__(self):
        return '%r' % self.data

    def __eq__(self, other):
        return isinstance(other, type(self)) and self.data == other.data
    def __hash__(self):
        return hash(self.data)


class Terminal_Regexp(Terminal):
    def __init__(self, data):
        Terminal.__init__(self, data)
        self.match = re.compile(data).match

class Terminal_Token(Terminal):
    def match(self, other):
        return self.data == other.type

