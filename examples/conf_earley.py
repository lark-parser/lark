#
# This example demonstrates parsing using the dynamic-lexer earley frontend
#
# Using a lexer for configuration files is tricky, because values don't
# have to be surrounded by delimiters. Using a standard lexer for this just won't work.
#
# In this example we use a dynamic lexer and let the Earley parser resolve the ambiguity.
#
# Another approach is to use the contextual lexer with LALR. It is less powerful than Earley,
# but it can handle some ambiguity when lexing and it's much faster.
# See examples/conf_lalr.py for an example of that approach.
#


from lark import Lark

parser = Lark(r"""
        start: _NL? section+
        section: "[" NAME "]" _NL item+
        item: NAME "=" VALUE? _NL
        VALUE: /./+

        %import common.CNAME -> NAME
        %import common.NEWLINE -> _NL
        %import common.WS_INLINE
        %ignore WS_INLINE
    """, parser="earley")

def test():
    sample_conf = """
[bla]

a=Hello
this="that",4
empty=
"""

    r = parser.parse(sample_conf)
    print (r.pretty())

if __name__ == '__main__':
    test()
