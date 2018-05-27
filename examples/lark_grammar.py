from lark import Lark

parser = Lark(open('examples/lark.lark'), parser="lalr")

grammar_files = [
    'examples/python2.lark',
    'examples/python3.lark',
    'examples/lark.lark',
    'lark/grammars/common.lark',
]

def test():
    for grammar_file in grammar_files:
        tree = parser.parse(open(grammar_file).read())
    print("All grammars parsed successfully")

if __name__ == '__main__':
    test()
