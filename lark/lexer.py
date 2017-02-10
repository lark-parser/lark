## Lexer Implementation

import re

from .utils import Str

class LexError(Exception):
    pass

class Token(Str):
    def __new__(cls, type, value, pos_in_stream=None):
        inst = Str.__new__(cls, value)
        inst.type = type
        inst.pos_in_stream = pos_in_stream
        inst.value = value
        return inst

    @classmethod
    def new_borrow_pos(cls, type, value, borrow_t):
        inst = cls(type, value, borrow_t.pos_in_stream)
        inst.line = borrow_t.line
        inst.column = borrow_t.column
        return inst

    def __repr__(self):
        return 'Token(%s, %s)' % (self.type, self.value)

class Regex:
    def __init__(self, pattern, flags=()):
        self.pattern = pattern
        self.flags = flags


class Lexer(object):
    def __init__(self, tokens, callbacks, ignore=()):
        self.ignore = ignore
        self.newline_char = '\n'
        tokens = list(tokens)

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

        self.token_types = list(token_names)
        self.type_index = {name:i for i,name in enumerate(self.token_types)}

        self.newline_types = [self.type_index[t[0]] for t in tokens if '\n' in t[1] or '\\n' in t[1] or '(?s)' in t[1]]
        self.ignore_types = [self.type_index[t] for t in ignore]

        self.mres = self._build_mres(tokens, len(tokens))


    def _build_mres(self, tokens, max_size):
        # Python sets an unreasonable group limit (currently 100) in its re module
        # Worse, the only way to know we reached it is by catching an AssertionError!
        # This function recursively tries less and less groups until it's successful.
        mres = []
        while tokens:
            try:
                mre = re.compile(u'|'.join(u'(?P<%s>%s)'%t for t in tokens[:max_size]))
            except AssertionError:  # Yes, this is what Python provides us.. :/
                return self._build_mres(tokens, max_size/2)

            mres.append((mre, {i:self.type_index[n] for n,i in mre.groupindex.items()} ))
            tokens = tokens[max_size:]
        return mres

    def lex(self, stream):
        lex_pos = 0
        line = 1
        col_start_pos = 0
        newline_types = list(self.newline_types)
        ignore_types = list(self.ignore_types)
        while True:
            for mre, type_from_index in self.mres:
                m = mre.match(stream, lex_pos)
                if m:
                    value = m.group(0)
                    type_num = type_from_index[m.lastindex]
                    if type_num not in ignore_types:
                        t = Token(self.token_types[type_num], value, lex_pos)
                        t.line = line
                        t.column = lex_pos - col_start_pos
                        if t.type in self.callbacks:
                            t = self.callbacks[t.type](t)
                        yield t

                    if type_num in newline_types:
                        newlines = value.count(self.newline_char)
                        if newlines:
                            line += newlines
                            col_start_pos = lex_pos + value.rindex(self.newline_char)
                    lex_pos += len(value)
                    break
            else:
                if lex_pos < len(stream):
                    context = stream[lex_pos:lex_pos+5]
                    raise LexError("No token defined for: '%s' in %s at line %d" % (stream[lex_pos], context, line))
                break


