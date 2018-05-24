from lark import Lark

parser = Lark(open('examples/lark.g'), parser="lalr")

grammar_files = [
    'examples/python2.g',
    'examples/python3.g',
    'examples/lark.g',
    'lark/grammars/common.g',
]

def test():
    for grammar_file in grammar_files:
        tree = parser.parse(open(grammar_file).read())
    print("All grammars parsed successfully")

if __name__ == '__main__':
    test()
