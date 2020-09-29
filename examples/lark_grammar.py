"""
Lark Grammar
============

A reference implementation of the Lark grammar (using LALR(1))
"""
import lark
from pathlib import Path

parser = lark.Lark.open('lark.lark', rel_to=__file__, parser="lalr")

examples_path = Path(__file__).parent
lark_path = Path(lark.__file__).parent

grammar_files = [
    examples_path / 'lark.lark',
    examples_path / 'advanced/python2.lark',
    examples_path / 'advanced/python3.lark',
    examples_path / 'relative-imports/multiples.lark',
    examples_path / 'relative-imports/multiple2.lark',
    examples_path / 'relative-imports/multiple3.lark',
    examples_path / 'tests/no_newline_at_end.lark',
    examples_path / 'tests/negative_priority.lark',
    lark_path / 'grammars/common.lark',
]

def test():
    for grammar_file in grammar_files:
        tree = parser.parse(open(grammar_file).read())
    print("All grammars parsed successfully")

if __name__ == '__main__':
    test()
