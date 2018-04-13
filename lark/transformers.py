import inspect
from functools import wraps

from . import utils
from .tree import Tree

class Discard(Exception):
    pass


class Base:
    def _call_userfunc(self, tree):
        return getattr(self, tree.data, self.__default__)(tree)

    def __default__(self, tree):
        return tree

class Transformer(Base):
    def _transform_children(self, children):
        for c in children:
            try:
                yield self._transform(c) if isinstance(c, Tree) else c
            except Discard:
                pass

    def _transform(self, tree):
        tree = Tree(tree.data, list(self._transform_children(tree.children)))
        return self._call_userfunc(tree)

    def transform(self, tree):
        return self._transform(tree)

    def __mul__(self, other):
        return TransformerChain(self, other)

class ChildrenTransformer(Transformer):
    def _call_userfunc(self, tree):
        # Assumes tree is already transformed
        try:
            f = getattr(self, tree.data)
        except AttributeError:
            return self.__default__(tree)
        else:
            return f(tree.children)

class ChildrenInlineTransformer(Transformer):
    def _call_userfunc(self, tree):
        # Assumes tree is already transformed
        try:
            f = getattr(self, tree.data)
        except AttributeError:
            return self.__default__(tree)
        else:
            return f(*tree.children)


class TransformerChain(object):
    def __init__(self, *transformers):
        self.transformers = transformers

    def transform(self, tree):
        for t in self.transformers:
            tree = t.transform(tree)
        return tree

    def __mul__(self, other):
        return TransformerChain(*self.transformers + (other,))


class Transformer_InPlace(Transformer):
    def _transform(self, tree):
        return self._call_userfunc(tree)

    def transform(self, tree):
        for subtree in tree.iter_subtrees():
            subtree.children = list(self._transform_children(subtree.children))

        return self._transform(tree)

class Visitor(Base):
    def visit(self, tree):
        for subtree in tree.iter_subtrees():
            self._call_userfunc(subtree)
        return tree

class Transformer_InPlaceRecursive(Transformer):
    def _transform(self, tree):
        tree.children = list(self._transform_children(tree.children))
        return self._call_userfunc(tree)

class Visitor_Recursive(Base):
    def visit(self, tree):
        for child in tree.children:
            if isinstance(child, Tree):
                self.visit(child)

        f = getattr(self, tree.data, self.__default__)
        f(tree)
        return tree


def inline_args(obj):
    if inspect.isclass(obj) and issubclass(obj, ChildrenTransformer):
        class _NewTransformer(ChildrenInlineTransformer, obj):
            pass
        return _NewTransformer
    else:
        return utils.inline_args(obj)

