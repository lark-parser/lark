#
# This example shows how to use get explicit ambiguity from Lark's Earley parser.
#

from lark import Lark

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

if __name__ == '__main__':
    print(parser.parse('fruit flies like bananas').pretty())

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
