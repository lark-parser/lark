"""
Extend the Python Grammar
==============================

This example demonstrates how to use the `%extend` statement,
to add new syntax to the example Python grammar.

"""

from lark.lark import Lark
from python_parser import PythonIndenter

GRAMMAR = r"""
%import python (compound_stmt, single_input, file_input, eval_input, test, suite, _NEWLINE, _INDENT, _DEDENT, COMMENT)

%extend compound_stmt: match_stmt

match_stmt: "match" test ":" cases
cases: _NEWLINE _INDENT case+ _DEDENT

case: "case" test ":" suite // test is not quite correct.

%ignore /[\t \f]+/          // WS
%ignore /\\[\t \f]*\r?\n/   // LINE_CONT
%ignore COMMENT
"""

parser = Lark(GRAMMAR, parser='lalr', start=['single_input', 'file_input', 'eval_input'], postlex=PythonIndenter())

tree = parser.parse(r"""
def name(n):
    match n:
        case 1:
            print("one")
        case 2:
            print("two")
        case _:
            print("number is too big")

""", start='file_input')

# Remove the 'python3__' prefix that was added to the implicitly imported rules.
for t in tree.iter_subtrees():
    t.data = t.data.rsplit('__', 1)[-1]

print(tree.pretty())
