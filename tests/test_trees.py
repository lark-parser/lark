from __future__ import absolute_import

import unittest
from functools import partial, reduce, partialmethod
from operator import add, mul
from unittest import TestCase
import copy
import pickle
import functools

from lark.tree import Tree
from lark.lexer import Token
from lark.visitors import Visitor, Visitor_Recursive, Transformer, Interpreter, visit_children_decor, v_args, Discard, Transformer_InPlace, \
    Transformer_InPlaceRecursive, Transformer_NonRecursive, merge_transformers


class TestTrees(TestCase):
    def setUp(self):
        self.tree1 = Tree('a', [Tree(x, y) for x, y in zip('bcd', 'xyz')])

    def test_eq(self):
        assert self.tree1 == self.tree1
        assert self.tree1 != 0

    def test_copy(self):
        assert self.tree1 == copy.copy(self.tree1)

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

    def test_smart_decorator(self):
        class OtherClass:
            @staticmethod
            def ab_staticmethod(a, b):
                return (a, b)

            @classmethod
            def ab_classmethod(cls, a, b):
                assert cls is OtherClass, cls
                return (a, b)

            def ab_method(self, a, b):
                assert isinstance(self, OtherClass), self
                return (a, b)

        @v_args(meta=True)
        class OtherTransformer(Transformer):
            @staticmethod
            def ab_staticmethod(meta, children):
                return tuple(children)

            @classmethod
            def ab_classmethod(cls, meta, children):
                assert cls is OtherTransformer, cls
                return tuple(children)

            def ab_method(self, meta, children):
                assert isinstance(self, OtherTransformer), self
                return tuple(children)

        class CustomCallable:
            def __call__(self, *args, **kwargs):
                assert isinstance(self, CustomCallable)
                return args

        oc_instance = OtherClass()
        ot_instance = OtherTransformer()

        def ab_for_partialmethod(self, a, b):
            assert isinstance(self, TestCls)
            return a, b

        @v_args(inline=True)
        class TestCls(Transformer):
            @staticmethod
            def ab_staticmethod(a, b):
                return (a, b)

            @classmethod
            def ab_classmethod(cls, a, b):
                assert cls is TestCls
                return (a, b)

            def ab_method(self, a, b):
                assert isinstance(self, TestCls)
                return (a, b)

            oc_class_ab_staticmethod = oc_instance.ab_staticmethod
            oc_class_ab_classmethod = oc_instance.ab_classmethod

            oc_ab_staticmethod = oc_instance.ab_staticmethod
            oc_ab_classmethod = oc_instance.ab_classmethod
            oc_ab_method = oc_instance.ab_method

            ot_class_ab_staticmethod = ot_instance.ab_staticmethod
            ot_class_ab_classmethod = ot_instance.ab_classmethod

            ot_ab_staticmethod = ot_instance.ab_staticmethod
            ot_ab_classmethod = ot_instance.ab_classmethod
            ot_ab_method = ot_instance.ab_method

            ab_partialmethod = partialmethod(ab_for_partialmethod, 1)
            set_union = set(["a"]).union
            static_add = staticmethod(add)
            partial_reduce_mul = partial(reduce, mul)

            custom_callable = CustomCallable()

        test_instance = TestCls()
        expected = {
            "ab_classmethod": ([1, 2], (1, 2)),
            "ab_staticmethod": ([1, 2], (1, 2)),
            "ab_method": ([1, 2], (1, 2)),
            "oc_ab_classmethod": ([1, 2], (1, 2)),
            "oc_class_ab_classmethod": ([1, 2], (1, 2)),

            # AFAIK, these two cases are impossible to deal with. `oc_instance.ab_staticmethod` returns an actual
            # function object that is impossible to distinguish from a normally defined method.
            # (i.e. `staticmethod(f).__get__(?, ?) is f` is True)
            # "oc_ab_staticmethod": ([1, 2], (1, 2)),
            # "oc_class_ab_staticmethod": ([1, 2], (1, 2)),

            "oc_ab_method": ([1, 2], (1, 2)),
            "ot_ab_classmethod": ([1, 2], (1, 2)),
            "ot_class_ab_classmethod": ([1, 2], (1, 2)),

            # Same as above
            # "ot_ab_staticmethod": ([1, 2], (1, 2)),
            # "ot_class_ab_staticmethod": ([1, 2], (1, 2)),

            "ot_ab_method": ([1, 2], (1, 2)),
            "ab_partialmethod": ([2], (1, 2)),
            "custom_callable": ([1, 2], (1, 2)),
            "set_union": ([["b"], ["c"]], {"a", "b", "c"}),
            "static_add": ([1, 2], 3),
            "partial_reduce_mul": ([[1, 2]], 2),
        }
        non_static = {"ab_method", "ab_partialmethod"}
        for method_name, (children, expected_result) in expected.items():
            not_inline = "ot" in method_name
            result = test_instance.transform(Tree(method_name, children))
            self.assertEqual(result, expected_result)

            if not_inline:
                result = getattr(test_instance, method_name)(None, children)
            else:
                result = getattr(test_instance, method_name)(*children)
            self.assertEqual(result, expected_result)

            if method_name not in non_static:
                if not_inline:
                    result = getattr(TestCls, method_name)(None, children)
                else:
                    result = getattr(TestCls, method_name)(*children)
                self.assertEqual(result, expected_result)

    def test_vargs_set_name(self):
        # Test with cached_property if available. That actually uses __set_name__
        prop = getattr(functools, "cached_property", property)

        class T(Transformer):
            @v_args(inline=True)
            @prop  # Not sure why you would ever want to use a property here, but we support it
            def test(self):
                return lambda a, b: (self, a, b)

        t = T()
        self.assertEqual(t.transform(Tree("test", [1, 2])), (t, 1, 2))

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
                return Discard

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
        tree = Tree('start', [
            Tree('add', [Token('N', '1'), Token('N', '2'), Token('IGNORE_TOKEN', '4')]),
            Tree('add', [Token('N', '3'), Token('N', '4')]),
            Tree('ignore_tree', [Token('DO', 'NOT PANIC')]),
            ])
        for base in (Transformer, Transformer_InPlace, Transformer_NonRecursive, Transformer_InPlaceRecursive):
            class T(base):
                def add(self, children):
                    return sum(children)

                def N(self, token):
                    return int(token)

                def ignore_tree(self, children):
                    return Discard

                def IGNORE_TOKEN(self, token):
                    return Discard

            copied = copy.deepcopy(tree)
            result = T().transform(copied)
            self.assertEqual(result, Tree('start', [3, 7]))

    def test_merge_transformers(self):
        tree = Tree('start', [
            Tree('main', [
                Token("A", '1'), Token("B", '2')
            ]),
            Tree("module__main", [
                Token("A", "2"), Token("B", "3")
            ])
        ])

        class T1(Transformer):
            A = int
            B = int
            main = sum
            start = list
            def module__main(self, children):
                return sum(children)

        class T2(Transformer):
            A = int
            B = int
            main = sum
            start = list

        class T3(Transformer):
            def main(self, children):
                return sum(children)

        class T4(Transformer):
            main = sum


        t1_res = T1().transform(tree)
        composed_res = merge_transformers(T2(), module=T3()).transform(tree)
        self.assertEqual(t1_res, composed_res)

        composed_res2 = merge_transformers(T2(), module=T4()).transform(tree)
        self.assertEqual(t1_res, composed_res2)

        with self.assertRaises(AttributeError):
            merge_transformers(T1(), module=T3())

    def test_transform_token(self):
        class MyTransformer(Transformer):
            def INT(self, value):
                return int(value)

        t = Token('INT', '123')
        assert MyTransformer().transform(t) == 123

        class MyTransformer(Transformer):
            def INT(self, value):
                return Discard

        assert MyTransformer().transform(t) is None


if __name__ == '__main__':
    unittest.main()
