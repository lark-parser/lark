#
# This example shows how to use get explicit ambiguity from Lark's Earley parser.
#

from lark import Lark

g = """
    sentence: noun verb noun        -> simple
            | noun verb "like" noun -> comparative

    noun: ADJ? NOUN
    verb: VERB

    NOUN: "flies" | "bananas" | "fruit"
    VERB: "like" | "flies"
    ADJ: "fruit"

    %import common.WS
    %ignore WS
"""

lark = Lark(g, start='sentence', ambiguity='explicit')

print(lark.parse('fruit flies like bananas').pretty())

# Outputs:
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

