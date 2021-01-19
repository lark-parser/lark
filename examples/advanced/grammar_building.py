from pathlib import Path

from lark.indenter import Indenter
from lark.lark import Lark
from lark.load_grammar import GrammarBuilder

MATCH_GRAMMAR = ('match', """

%extend compound_stmt: match_stmt

match_stmt: "match" test ":" cases

cases: _NEWLINE _INDENT case+ _DEDENT

case: "case" test ":" suite // test is not quite correct. 

""", ('compound_stmt', 'test', 'suite', '_DEDENT', '_INDENT', '_NEWLINE'))

EXTENSIONS = (MATCH_GRAMMAR,)

builder = GrammarBuilder()

builder.load_grammar((Path(__file__).with_name('python3.lark')).read_text(), 'python3')

for name, ext_grammar, needed_names in EXTENSIONS:
    mangle = builder.get_mangle(name, dict(zip(needed_names, needed_names)))
    builder.load_grammar(ext_grammar, name, mangle)

grammar = builder.build()


class PythonIndenter(Indenter):
    NL_type = '_NEWLINE'
    OPEN_PAREN_types = ['LPAR', 'LSQB', 'LBRACE']
    CLOSE_PAREN_types = ['RPAR', 'RSQB', 'RBRACE']
    INDENT_type = '_INDENT'
    DEDENT_type = '_DEDENT'
    tab_len = 8


parser = Lark(grammar, parser='lalr', start=['single_input', 'file_input', 'eval_input'], postlex=PythonIndenter())

tree = parser.parse(r"""

a = 5

def name(n):
    match n:
        case 1:
            print("one")
        case 2:
            print("two")
        case _:
            print("number is to big") 

name(a)
""", start='file_input')

print(tree.pretty())
