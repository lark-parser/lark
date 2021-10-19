"""
Transform a Forest
==================

This example demonstrates how to subclass ``TreeForestTransformer`` to
directly transform a SPPF.
"""

from lark import Lark
from lark.parsers.earley_forest import TreeForestTransformer, handles_ambiguity, Discard

class CustomTransformer(TreeForestTransformer):

    @handles_ambiguity
    def sentence(self, trees):
        return next(tree for tree in trees if tree.data == 'simple')

    def simple(self, children):
        children.append('.')
        return self.tree_class('simple', children)

    def adj(self, children):
        return Discard

    def __default_token__(self, token):
        return token.capitalize()

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

parser = Lark(grammar, start='sentence', ambiguity='forest')
sentence = 'fruit flies like bananas'
forest = parser.parse(sentence)

tree = CustomTransformer(resolve_ambiguity=False).transform(forest)
print(tree.pretty())

# Output:
#
# simple
#   noun  Flies
#   verb  Like
#   noun  Bananas
#   .
#
