from __future__ import absolute_import

import unittest
from unittest import TestCase
import copy
import pickle
import functools

from lark.tree import Tree
from lark.lexer import Token
from lark.visitors import Visitor, Visitor_Recursive, Transformer, Interpreter, visit_children_decor, v_args, Discard, Transformer_InPlace, \
    Transformer_InPlaceRecursive, Transformer_NonRecursive


class TestTrees(TestCase):
    def setUp(self):
        self.tree1 = Tree('a', [Tree(x, y) for x, y in zip('bcd', 'xyz')])

    def test_deepcopy(self):
        assert self.tree1 == copy.deepcopy(self.tree1)

    def test_pickle(self):
        s = copy.deepcopy(self.tree1)
        data = pickle.dumps(s, protocol=pickle.HIGHEST_PROTOCOL)
        assert pickle.loads(data) == s

    def test_repr_runnable(self):
        assert self.tree1 == eval(repr(self.tree1))

    def test_iter_subtrees(self):
        expected = [Tree('b', 'x'), Tree('c', 'y'), Tree('d', 'z'),
                    Tree('a', [Tree('b', 'x'), Tree('c', 'y'), Tree('d', 'z')])]
        nodes = list(self.tree1.iter_subtrees())
        self.assertEqual(nodes, expected)

    def test_iter_subtrees_topdown(self):
        expected = [Tree('a', [Tree('b', 'x'), Tree('c', 'y'), Tree('d', 'z')]),
                    Tree('b', 'x'), Tree('c', 'y'), Tree('d', 'z')]
        nodes = list(self.tree1.iter_subtrees_topdown())
        self.assertEqual(nodes, expected)

    def test_visitor(self):
        class Visitor1(Visitor):
            def __init__(self):
                self.nodes=[]

            def __default__(self,tree):
                self.nodes.append(tree)
        class Visitor1_Recursive(Visitor_Recursive):
            def __init__(self):
                self.nodes=[]

            def __default__(self,tree):
                self.nodes.append(tree)

        visitor1=Visitor1()
        visitor1_recursive=Visitor1_Recursive()

        expected_top_down = [Tree('a', [Tree('b', 'x'), Tree('c', 'y'), Tree('d', 'z')]),
                    Tree('b', 'x'), Tree('c', 'y'), Tree('d', 'z')]
        expected_botton_up= [Tree('b', 'x'), Tree('c', 'y'), Tree('d', 'z'),
                    Tree('a', [Tree('b', 'x'), Tree('c', 'y'), Tree('d', 'z')])]

        visitor1.visit(self.tree1)
        self.assertEqual(visitor1.nodes,expected_botton_up)

        visitor1_recursive.visit(self.tree1)
        self.assertEqual(visitor1_recursive.nodes,expected_botton_up)

        visitor1.nodes=[]
        visitor1_recursive.nodes=[]

        visitor1.visit_topdown(self.tree1)
        self.assertEqual(visitor1.nodes,expected_top_down)

        visitor1_recursive.visit_topdown(self.tree1)
        self.assertEqual(visitor1_recursive.nodes,expected_top_down)

    def test_interp(self):
        t = Tree('a', [Tree('b', []), Tree('c', []), 'd'])

        class Interp1(Interpreter):
            def a(self, tree):
                return self.visit_children(tree) + ['e']

            def b(self, tree):
                return 'B'

            def c(self, tree):
                return 'C'

        self.assertEqual(Interp1().visit(t), list('BCde'))

        class Interp2(Interpreter):
            @visit_children_decor
            def a(self, values):
                return values + ['e']

            def b(self, tree):
                return 'B'

            def c(self, tree):
                return 'C'

        self.assertEqual(Interp2().visit(t), list('BCde'))

        class Interp3(Interpreter):
            def b(self, tree):
                return 'B'

            def c(self, tree):
                return 'C'

        self.assertEqual(Interp3().visit(t), list('BCd'))

    def test_transformer(self):
        t = Tree('add', [Tree('sub', [Tree('i', ['3']), Tree('f', ['1.1'])]), Tree('i', ['1'])])

        class T(Transformer):
            i = v_args(inline=True)(int)
            f = v_args(inline=True)(float)

            sub = lambda self, values: values[0] - values[1]

            def add(self, values):
                return sum(values)

        res = T().transform(t)
        self.assertEqual(res, 2.9)

        @v_args(inline=True)
        class T(Transformer):
            i = int
            f = float
            sub = lambda self, a, b: a-b

            def add(self, a, b):
                return a + b


        res = T().transform(t)
        self.assertEqual(res, 2.9)


        @v_args(inline=True)
        class T(Transformer):
            i = int
            f = float
            from operator import sub, add

        res = T().transform(t)
        self.assertEqual(res, 2.9)

    def test_vargs(self):
        @v_args()
        class MyTransformer(Transformer):
            @staticmethod
            def integer(args):
                return 1 # some code here

            @classmethod
            def integer2(cls, args):
                return 2 # some code here

            hello = staticmethod(lambda args: 'hello')

        x = MyTransformer().transform( Tree('integer', [2]))
        self.assertEqual(x, 1)
        x = MyTransformer().transform( Tree('integer2', [2]))
        self.assertEqual(x, 2)
        x = MyTransformer().transform( Tree('hello', [2]))
        self.assertEqual(x, 'hello')

    def test_inline_static(self):
        @v_args(inline=True)
        class T(Transformer):
            @staticmethod
            def test(a, b):
                return a + b
        x = T().transform(Tree('test', ['a', 'b']))
        self.assertEqual(x, 'ab')

    def test_vargs_override(self):
        t = Tree('add', [Tree('sub', [Tree('i', ['3']), Tree('f', ['1.1'])]), Tree('i', ['1'])])

        @v_args(inline=True)
        class T(Transformer):
            i = int
            f = float
            sub = lambda self, a, b: a-b

            not_a_method = {'other': 'stuff'}

            @v_args(inline=False)
            def add(self, values):
                return sum(values)

        res = T().transform(t)
        self.assertEqual(res, 2.9)

    def test_partial(self):

        tree = Tree("start", [Tree("a", ["test1"]), Tree("b", ["test2"])])

        def test(prefix, s, postfix):
            return prefix + s.upper() + postfix

        @v_args(inline=True)
        class T(Transformer):
            a = functools.partial(test, "@", postfix="!")
            b = functools.partial(lambda s: s + "!")

        res = T().transform(tree)
        assert res.children == ["@TEST1!", "test2!"]


    def test_discard(self):
        class MyTransformer(Transformer):
            def a(self, args):
                return 1 # some code here

            def b(cls, args):
                raise Discard()

        t = Tree('root', [
            Tree('b', []),
            Tree('a', []),
            Tree('b', []),
            Tree('c', []),
            Tree('b', []),
        ])
        t2 = Tree('root', [1, Tree('c', [])])

        x = MyTransformer().transform( t )
        self.assertEqual(x, t2)
    
    def test_transformer_variants(self):
        tree = Tree('start', [Tree('add', [Token('N', '1'), Token('N', '2')]), Tree('add', [Token('N', '3'), Token('N', '4')])])
        for base in (Transformer, Transformer_InPlace, Transformer_NonRecursive, Transformer_InPlaceRecursive):
            class T(base):
                def add(self, children):
                    return sum(children)
                
                def N(self, token):
                    return int(token)
            
            copied = copy.deepcopy(tree)
            result = T().transform(copied)
            self.assertEqual(result, Tree('start', [3, 7]))


if __name__ == '__main__':
    unittest.main()
