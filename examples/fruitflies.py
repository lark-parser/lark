#
# This example shows how to use get explicit ambiguity from Lark's Earley parser.
#

import sys
from lark import Lark, tree

grammar = """
    sentence: noun verb noun        -> simple
            | noun verb "like" noun -> comparative

    noun: adj? NOUN
    verb: VERB
    adj: ADJ

    NOUN: "flies" | "bananas" | "fruit"
    VERB: "like" | "flies"
    ADJ: "fruit"

    %import common.WS
    %ignore WS
"""

parser = Lark(grammar, start='sentence', ambiguity='explicit')

sentence = 'fruit flies like bananas'

def make_png(filename):
    tree.pydot__tree_to_png( parser.parse(sentence), filename)

if __name__ == '__main__':
    print(parser.parse(sentence).pretty())
    # make_png(sys.argv[1])

# Output:
#
# _ambig
#   comparative
#     noun	fruit
#     verb	flies
#     noun	bananas
#   simple
#     noun
#       fruit
#       flies
#     verb	like
#     noun	bananas
#
# (or view a nicer version at "./fruitflies.png")
