from __future__ import absolute_import

import unittest

from lark import Lark
from lark.lexer import Token
from lark.tree import Tree
from lark.visitors import Visitor, Transformer, Discard
from lark.parsers.earley_forest import TreeForestTransformer, handles_ambiguity

class TestTreeForestTransformer(unittest.TestCase):

    grammar = """
    start: ab bc cd
    !ab: "A" "B"?
    !bc: "B"? "C"?
    !cd: "C"? "D"
    """

    parser = Lark(grammar, parser='earley', ambiguity='forest')
    forest = parser.parse("ABCD")

    def test_identity_resolve_ambiguity(self):
        l = Lark(self.grammar, parser='earley', ambiguity='resolve')
        tree1 = l.parse("ABCD")
        tree2 = TreeForestTransformer(resolve_ambiguity=True).transform(self.forest)
        self.assertEqual(tree1, tree2)

    def test_identity_explicit_ambiguity(self):
        l = Lark(self.grammar, parser='earley', ambiguity='explicit')
        tree1 = l.parse("ABCD")
        tree2 = TreeForestTransformer(resolve_ambiguity=False).transform(self.forest)
        self.assertEqual(tree1, tree2)

    def test_tree_class(self):

        class CustomTree(Tree):
            pass

        class TreeChecker(Visitor):
            def __default__(self, tree):
                assert isinstance(tree, CustomTree)

        tree = TreeForestTransformer(resolve_ambiguity=False, tree_class=CustomTree).transform(self.forest)
        TreeChecker().visit(tree)

    def test_token_calls(self):

        visited = [False] * 4

        class CustomTransformer(TreeForestTransformer):
            def A(self, node):
                assert node.type == 'A'
                visited[0] = True
            def B(self, node):
                assert node.type == 'B'
                visited[1] = True
            def C(self, node):
                assert node.type == 'C'
                visited[2] = True
            def D(self, node):
                assert node.type == 'D'
                visited[3] = True

        tree = CustomTransformer(resolve_ambiguity=False).transform(self.forest)
        assert visited == [True] * 4

    def test_default_token(self):

        token_count = [0]

        class CustomTransformer(TreeForestTransformer):
            def __default_token__(self, node):
                token_count[0] += 1
                assert isinstance(node, Token)

        tree = CustomTransformer(resolve_ambiguity=True).transform(self.forest)
        self.assertEqual(token_count[0], 4)

    def test_rule_calls(self):

        visited_start = [False]
        visited_ab = [False]
        visited_bc = [False]
        visited_cd = [False]

        class CustomTransformer(TreeForestTransformer):
            def start(self, data):
                visited_start[0] = True
            def ab(self, data):
                visited_ab[0] = True
            def bc(self, data):
                visited_bc[0] = True
            def cd(self, data):
                visited_cd[0] = True

        tree = CustomTransformer(resolve_ambiguity=False).transform(self.forest)
        self.assertTrue(visited_start[0])
        self.assertTrue(visited_ab[0])
        self.assertTrue(visited_bc[0])
        self.assertTrue(visited_cd[0])

    def test_default_rule(self):

        rule_count = [0]

        class CustomTransformer(TreeForestTransformer):
            def __default__(self, name, data):
                rule_count[0] += 1

        tree = CustomTransformer(resolve_ambiguity=True).transform(self.forest)
        self.assertEqual(rule_count[0], 4)

    def test_default_ambig(self):

        ambig_count = [0]

        class CustomTransformer(TreeForestTransformer):
            def __default_ambig__(self, name, data):
                if len(data) > 1:
                    ambig_count[0] += 1

        tree = CustomTransformer(resolve_ambiguity=False).transform(self.forest)
        self.assertEqual(ambig_count[0], 1)

    def test_handles_ambiguity(self):

        class CustomTransformer(TreeForestTransformer):
            @handles_ambiguity
            def start(self, data):
                assert isinstance(data, list)
                assert len(data) == 4
                for tree in data:
                    assert tree.data == 'start'
                return 'handled'

            @handles_ambiguity
            def ab(self, data):
                assert isinstance(data, list)
                assert len(data) == 1
                assert data[0].data == 'ab'

        tree = CustomTransformer(resolve_ambiguity=False).transform(self.forest)
        self.assertEqual(tree, 'handled')

    def test_discard(self):

        class CustomTransformer(TreeForestTransformer):
            def bc(self, data):
                raise Discard()

            def D(self, node):
                raise Discard()

        class TreeChecker(Transformer):
            def bc(self, children):
                assert False

            def D(self, token):
                assert False

        tree = CustomTransformer(resolve_ambiguity=False).transform(self.forest)
        TreeChecker(visit_tokens=True).transform(tree)

    def test_aliases(self):

        visited_ambiguous = [False]
        visited_full = [False]

        class CustomTransformer(TreeForestTransformer):
            @handles_ambiguity
            def start(self, data):
                for tree in data:
                    assert tree.data == 'ambiguous' or tree.data == 'full'

            def ambiguous(self, data):
                visited_ambiguous[0] = True
                assert len(data) == 3
                assert data[0].data == 'ab'
                assert data[1].data == 'bc'
                assert data[2].data == 'cd'
                return self.tree_class('ambiguous', data)

            def full(self, data):
                visited_full[0] = True
                assert len(data) == 1
                assert data[0].data == 'abcd'
                return self.tree_class('full', data)

        grammar = """
        start: ab bc cd -> ambiguous
            | abcd -> full
        !ab: "A" "B"?
        !bc: "B"? "C"?
        !cd: "C"? "D"
        !abcd: "ABCD"
        """

        l = Lark(grammar, parser='earley', ambiguity='forest')
        forest = l.parse('ABCD')
        tree = CustomTransformer(resolve_ambiguity=False).transform(forest)
        self.assertTrue(visited_ambiguous[0])
        self.assertTrue(visited_full[0])

    def test_transformation(self):

        class CustomTransformer(TreeForestTransformer):
            def __default__(self, name, data):
                result = []
                for item in data:
                    if isinstance(item, list):
                        result += item
                    else:
                        result.append(item)
                return result

            def __default_token__(self, node):
                return node.lower()

            def __default_ambig__(self, name, data):
                return data[0]

        result = CustomTransformer(resolve_ambiguity=False).transform(self.forest)
        expected = ['a', 'b', 'c', 'd']
        self.assertEqual(result, expected)

if __name__ == '__main__':
    unittest.main()
