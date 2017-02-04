## Lexer Implementation
from utils import Str

class LexError(Exception):
    pass

class Token(Str):
    def __new__(cls, type, value, pos_in_stream=None):
        inst = Str.__new__(cls, value)
        inst.type = type
        inst.pos_in_stream = pos_in_stream
        inst.value = value
        return inst

# class Token(object):
#     def __init__(self, type, value, lexpos):
#         self.type = type
#         self.value = value
#         self.lexpos = lexpos


    def __repr__(self):
        return 'Token(%s, %s, %s)' % (self.type, self.value, self.pos_in_stream)

class Regex:
    def __init__(self, pattern, flags=()):
        self.pattern = pattern
        self.flags = flags


import re
LIMIT = 50 # Stupid named groups limit in python re
class Lexer(object):
    def __init__(self, tokens, callbacks, ignore=()):
        self.ignore = ignore

        # Sanitization
        token_names = {t[0] for t in tokens}
        for t in tokens:
            try:
                re.compile(t[1])
            except:
                raise LexError("Cannot compile token: %s: %s" % t)
        assert all(t in token_names for t in ignore)

        # Init
        self.tokens = tokens
        self.callbacks = callbacks

        self.tokens.sort(key=lambda x:len(x[1]), reverse=True)

        self.mres = []
        self.name_from_index = []
        x = tokens
        while x:
            mre =  re.compile(u'|'.join(u'(?P<%s>%s)'%t for t in x[:LIMIT]))
            self.mres.append(mre)
            self.name_from_index.append( {i:n for n,i in mre.groupindex.items()} )
            x = x[LIMIT:]

    def lex(self, stream):
        lex_pos = 0
        while True:
            i = 0
            for mre in self.mres:
                m = mre.match(stream, lex_pos)
                if m:
                    value = m.group(0)
                    type_ = self.name_from_index[i][m.lastindex]
                    t = Token(type_, value, lex_pos)
                    if t.type in self.callbacks:
                        self.callbacks[t.type](t)
                    if t.type not in self.ignore:
                        yield t
                    lex_pos += len(value)
                    break
                i += 1
            else:
                if lex_pos < len(stream):
                    context = stream[lex_pos:lex_pos+5]
                    raise LexError("No token defined for: '%s' in %s" % (stream[lex_pos], context))
                break


