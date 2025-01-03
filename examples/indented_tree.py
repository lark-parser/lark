"""
Parsing Indentation
===================

A demonstration of parsing indentation (“whitespace significant” language)
and the usage of the ``Indenter`` class.

Since indentation is context-sensitive, a postlex stage is introduced to
manufacture ``INDENT``/``DEDENT`` tokens.

It is crucial for the indenter that the ``NL_type`` matches the spaces (and
tabs) after the newline.

If your whitespace-significant grammar supports comments, then ``NL_type``
must match those comments too. Otherwise, comments that appear in the middle
of a line will `confuse Lark`_.

.. _`confuse Lark`: https://github.com/lark-parser/lark/issues/863
"""
from lark import Lark
from lark.indenter import Indenter

tree_grammar = r"""
    %import common.CNAME -> NAME
    %import common.WS_INLINE
    %import common.SH_COMMENT
    %ignore WS_INLINE
    %ignore SH_COMMENT
    %declare _INDENT _DEDENT

    ?start: _NL* tree
    tree: NAME _NL [_INDENT tree+ _DEDENT]
    _NL: (/\r?\n[\t ]*/ | SH_COMMENT)+
"""

class TreeIndenter(Indenter):
    NL_type = '_NL'
    OPEN_PAREN_types = []
    CLOSE_PAREN_types = []
    INDENT_type = '_INDENT'
    DEDENT_type = '_DEDENT'
    tab_len = 8

parser = Lark(tree_grammar, parser='lalr', postlex=TreeIndenter())

test_tree = """
a
    # check this comment out
    b
    c
        d
        e
    f
        g
"""

def test():
    print(parser.parse(test_tree).pretty())

if __name__ == '__main__':
    test()
