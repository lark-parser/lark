from functools import wraps

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

class Transformer_Children(Transformer):
    def _call_userfunc(self, tree):
        # Assumes tree is already transformed
        try:
            f = getattr(self, tree.data)
        except AttributeError:
            return self.__default__(tree)
        else:
            return f(tree.children)

class Transformer_ChildrenInline(Transformer):
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

class Visitor(Base):
    # def visit(self, tree):
    #     for child in tree.children:
    #         if isinstance(child, Tree):
    #             self.visit(child)

    #     f = getattr(self, tree.data, self.__default__)
    #     f(tree)
    #     return tree

    def visit(self, tree):
        for subtree in tree.iter_subtrees():
            self._call_userfunc(subtree)
        return tree

    def __default__(self, tree):
        pass


class InPlaceTransformer(Transformer):
    # def _transform(self, tree):
    #     children = []
    #     for c in tree.children:
    #         try:
    #             children.append(self._transform(c) if isinstance(c, Tree) else c)
    #         except Discard:
    #             pass

    #     tree.children = children
    #     return self._call_userfunc(tree)

    def _transform(self, tree):
        return self._call_userfunc(tree)

    def transform(self, tree):
        for subtree in tree.iter_subtrees():
            subtree.children = list(self._transform_children(subtree.children))

        return self._transform(tree)


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


