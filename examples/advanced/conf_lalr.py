"""
LALR’s contextual lexer
=======================

This example demonstrates the power of LALR's contextual lexer,
by parsing a toy configuration language.

The terminals `NAME` and `VALUE` overlap. They can match the same input.
A basic lexer would arbitrarily choose one over the other, based on priority,
which would lead to a (confusing) parse error.
However, due to the unambiguous structure of the grammar, Lark's LALR(1) algorithm knows
which one of them to expect at each point during the parse.
The lexer then only matches the tokens that the parser expects.
The result is a correct parse, something that is impossible with a regular lexer.

Another approach is to use the Earley algorithm.
It will handle more cases than the contextual lexer, but at the cost of performance.
See examples/conf_earley.py for an example of that approach.
"""
from lark import Lark

parser = Lark(r"""
        start: _NL? section+
        section: "[" NAME "]" _NL item+
        item: NAME "=" VALUE? _NL

        NAME: /\w/+
        VALUE: /./+

        %import common.NEWLINE -> _NL
        %import common.WS_INLINE
        %ignore WS_INLINE
    """, parser="lalr")


sample_conf = """
[bla]
a=Hello
this="that",4
empty=
"""

print(parser.parse(sample_conf).pretty())
