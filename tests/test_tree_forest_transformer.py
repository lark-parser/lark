from __future__ import absolute_import

import unittest

from lark import Lark
from lark.tree import Tree
from lark.visitors import Visitor
from lark.parsers.earley_forest import TreeForestTransformer, handles_ambiguity

class TestTreeForestTransformer(unittest.TestCase):

    def test_identity_resolve_ambiguity(self):

        grammar = """
        start: ab bc cd
        !ab: "A" "B"?
        !bc: "B"? "C"?
        !cd: "C"? "D"
        """

        l1 = Lark(grammar, parser='earley', ambiguity='resolve')
        l2 = Lark(grammar, parser='earley', ambiguity='forest')

        tree1 = l1.parse("ABCD")
        forest = l2.parse("ABCD")
        tree2 = TreeForestTransformer(resolve_ambiguity=True).transform(forest)

        self.assertEqual(tree1, tree2)

    def test_identity_explicit_ambiguity(self):

        grammar = """
        start: ab bc cd
        !ab: "A" "B"?
        !bc: "B"? "C"?
        !cd: "C"? "D"
        """

        l1 = Lark(grammar, parser='earley', ambiguity='explicit')
        l2 = Lark(grammar, parser='earley', ambiguity='forest')

        tree1 = l1.parse("ABCD")
        forest = l2.parse("ABCD")
        tree2 = TreeForestTransformer(resolve_ambiguity=False).transform(forest)

        self.assertEqual(tree1, tree2)

    def test_tree_class(self):

        class CustomTree(Tree):
            pass

        class TreeChecker(Visitor):
            def __default__(self, tree):
                assert isinstance(tree, CustomTree)

        grammar = """
        start: ab bc cd
        !ab: "A" "B"?
        !bc: "B"? "C"?
        !cd: "C"? "D"
        """

        l = Lark(grammar, parser='earley', ambiguity='forest')

        forest = l.parse("ABCD")
        tree = TreeForestTransformer(resolve_ambiguity=False, tree_class=CustomTree).transform(forest)
        TreeChecker().visit(tree)

    def test_token_calls(self):

        visited_A = False
        visited_B = False
        visited_C = False
        visited_D = False

        class CustomTransformer(TreeForestTransformer):
            def A(self, node):
                assert node.type == 'A'
                nonlocal visited_A
                visited_A = True
            def B(self, node):
                assert node.type == 'B'
                nonlocal visited_B
                visited_B = True
            def C(self, node):
                assert node.type == 'C'
                nonlocal visited_C
                visited_C = True
            def D(self, node):
                assert node.type == 'D'
                nonlocal visited_D
                visited_D = True

        grammar = """
        start: ab bc cd
        !ab: "A" "B"?
        !bc: "B"? "C"?
        !cd: "C"? "D"
        """

        l = Lark(grammar, parser='earley', ambiguity='forest')

        forest = l.parse("ABCD")
        tree = CustomTransformer(resolve_ambiguity=False).transform(forest)
        self.assertTrue(visited_A)
        self.assertTrue(visited_B)
        self.assertTrue(visited_C)
        self.assertTrue(visited_D)

    def test_default_token(self):

        token_count = 0

        class CustomTransformer(TreeForestTransformer):
            def __default_token__(self, node):
                nonlocal token_count
                token_count += 1

        grammar = """
        start: ab bc cd
        !ab: "A" "B"?
        !bc: "B"? "C"?
        !cd: "C"? "D"
        """

        l = Lark(grammar, parser='earley', ambiguity='forest')

        forest = l.parse("ABCD")
        tree = CustomTransformer(resolve_ambiguity=True).transform(forest)
        self.assertEqual(token_count, 4)

    def test_rule_call(self):

        visited_start = False
        visited_ab = False
        visited_bc = False
        visited_cd = False

        class CustomTransformer(TreeForestTransformer):
            def start(self, node, data):
                nonlocal visited_start
                visited_start = True
            def ab(self, node, data):
                nonlocal visited_ab
                visited_ab = True
            def bc(self, node, data):
                nonlocal visited_bc
                visited_bc = True
            def cd(self, node, data):
                nonlocal visited_cd
                visited_cd = True

        grammar = """
        start: ab bc cd
        !ab: "A" "B"?
        !bc: "B"? "C"?
        !cd: "C"? "D"
        """

        l = Lark(grammar, parser='earley', ambiguity='forest')

        forest = l.parse("ABCD")
        tree = CustomTransformer(resolve_ambiguity=False).transform(forest)
        self.assertTrue(visited_start)
        self.assertTrue(visited_ab)
        self.assertTrue(visited_bc)
        self.assertTrue(visited_cd)

    

if __name__ == '__main__':
    unittest.main()
