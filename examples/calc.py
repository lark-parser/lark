from lark import Lark, InlineTransformer

calc_grammar = """
    ?start: sum
          | NAME "=" sum    -> assign_var

    ?sum: product
        | sum "+" product   -> add
        | sum "-" product   -> sub

    ?product: atom
        | product "*" atom  -> mul
        | product "/" atom  -> div

    ?atom: /[\d.]+/         -> number
         | "-" atom         -> neg
         | NAME             -> var
         | "(" sum ")"

    NAME: /\w+/
    WS.ignore: /\s+/
"""

class CalculateTree(InlineTransformer):
    from operator import add, sub, mul, div, neg
    number = float

    def __init__(self):
        self.vars = {}

    def assign_var(self, name, value):
        self.vars[name] = value
        return value

    def var(self, name):
        return self.vars[name]



calc_parser = Lark(calc_grammar, parser='lalr', transformer=CalculateTree())
calc = calc_parser.parse

def main():
    while True:
        try:
            s = raw_input('> ')
        except EOFError:
            break
        print(calc(s))

def test():
    # print calc("a=(1+2)")
    print calc("a = 1+2")
    print calc("1+a*-3")

if __name__ == '__main__':
    test()
    # main()

