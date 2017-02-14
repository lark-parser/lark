#
# This example demonstrates lex-less parsing using the earley_nolex frontend
#
# Using a lexer for configuration files is tricky, because values don't
# have to be surrounded by delimiters.
# In this example with skip lexing and let the Earley parser resolve the ambiguity.
#
# Future versions of lark will make it easier to write these kinds of grammars.
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
    """, parser="earley_nolex")

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
