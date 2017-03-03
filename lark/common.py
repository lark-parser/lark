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
    return isinstance(sym, tuple) or sym.isupper() or sym[0] == '$'


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
    def __init__(self, value):
        self.value = value

    def __repr__(self):
        return repr(self.value)

    # Pattern Hashing assumes all subclasses have a different priority!
    def __hash__(self):
        return hash((self.priority, self.value))
    def __eq__(self, other):
        return self.priority == other.priority and self.value == other.value

class PatternStr(Pattern):
    def to_regexp(self):
        return re.escape(self.value)

    priority = 0

class PatternRE(Pattern):
    def to_regexp(self):
        return self.value

    priority = 1

class TokenDef(object):
    def __init__(self, name, pattern):
        assert isinstance(pattern, Pattern), pattern
        self.name = name
        self.pattern = pattern

    def __repr__(self):
        return '%s(%r, %r)' % (type(self).__name__, self.name, self.pattern)

