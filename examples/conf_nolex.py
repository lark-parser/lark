#
# This example demonstrates scanless parsing using the earley_nolex frontend
#
# Using a lexer for configuration files is tricky, because values don't
# have to be surrounded by delimiters.
# In this example with skip lexing and let the Earley parser resolve the ambiguity.
#
# Future versions of lark will make it easier to write these kinds of grammars.
#
# Another approach is to use the contextual lexer. It is less powerful than the scanless approach,
# but it can handle some ambiguity in lexing and it's much faster since it uses LALR(1).
# See examples/conf.py for an example of that approach.
#

from lark import Lark, Transformer

parser = Lark(r"""
        start: _nl? section+
        section: "[" name "]" _nl item+
        item: name "=" value _nl
        name: /[a-zA-Z_]/ /\w/*
        value: /./+
        _nl: (_CR? _LF)+

        _CR : /\r/
        _LF : /\n/
    """, lexer=None)

class RestoreTokens(Transformer):
    value = ''.join
    name = ''.join


def test():
    sample_conf = """
[bla]

a=Hello
this="that",4
"""

    r = parser.parse(sample_conf)
    print(RestoreTokens().transform(r).pretty())

if __name__ == '__main__':
    test()
