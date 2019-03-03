#
# This example demonstrates relative imports with rule rewrite
# see multiples.lark
#

#
# if b is a number written in binary, and m is either 2 or 3,
# the grammar aims to recognise m:b iif b is a multiple of m
#
# for example, 3:1001 is recognised
# because 9 (0b1001) is a multiple of 3
#

from lark import Lark, UnexpectedInput

parser = Lark.open('multiples.lark', parser='lalr')

def is_in_grammar(data):
    try:
        parser.parse(data)
    except UnexpectedInput:
        return False
    return True

for n_dec in range(100):
    n_bin = bin(n_dec)[2:]
    assert is_in_grammar('2:{}'.format(n_bin)) == (n_dec % 2 == 0)
    assert is_in_grammar('3:{}'.format(n_bin)) == (n_dec % 3 == 0)
