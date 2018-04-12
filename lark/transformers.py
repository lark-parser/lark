from functools import wraps

from .tree import Tree

class Discard(Exception):
    pass


class Transformer:
    def _get_userfunc(self, name):
        return getattr(self, name)

    def _call_userfunc(self, tree):
        # Assumes tree is already transformed
        try:
            f = self._get_userfunc(tree.data)
        except AttributeError:
            return self.__default__(tree)
        else:
            return f(tree)

    def _transform(self, tree):
        children = []
        for c in tree.children:
            try:
                children.append(self._transform(c) if isinstance(c, Tree) else c)
            except Discard:
                pass

        tree = Tree(tree.data, children)
        return self._call_userfunc(tree)

    def __default__(self, tree):
        return tree

    def transform(self, tree):
        return self._transform(tree)

    def __mul__(self, other):
        return TransformerChain(self, other)

class Transformer_Children(Transformer):
    def _call_userfunc(self, tree):
        # Assumes tree is already transformed
        try:
            f = self._get_userfunc(tree.data)
        except AttributeError:
            return self.__default__(tree)
        else:
            return f(tree.children)

class Transformer_ChildrenInline(Transformer):
    def _call_userfunc(self, tree):
        # Assumes tree is already transformed
        try:
            f = self._get_userfunc(tree.data)
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



#### XXX PSEUDOCODE TODO
# def items(obj):
#     if isinstance(obj, Transformer):
#         def new_get_userfunc(self, name):
#             uf = self._get_userfunc(name)
#             def _f(tree):
#                 return uf(tree.children)
#             return _f
#         obj._get_userfunc = new_get_userfunc
#     else:
#         assert callable(obj)
#         # apply decorator
#         def _f(tree):
#             return obj(tree.children)
#         return _f


