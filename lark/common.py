
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

        context = ' '.join(['%r(%s)' % (t.value, t.type) for t in seq[index:index+5]])
        message = ("Unexpected token %r at line %s, column %s.\n"
                   "Expected: %s\n"
                   "Context: %s" % (token.value, self.line, self.column, expected, context))

        super(ParseError, self).__init__(message)



def is_terminal(sym):
    return sym.isupper() or sym[0] == '$'


class LexerConf:
    def __init__(self, tokens, ignore, postlex):
        self.tokens = tokens
        self.ignore = ignore
        self.postlex = postlex

class ParserConf:
    def __init__(self, rules, callback, start):
        self.rules = rules
        self.callback = callback
        self.start = start
