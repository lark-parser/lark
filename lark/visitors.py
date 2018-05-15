from inspect import isclass, getmembers, getmro
from functools import wraps

from .utils import smart_decorator
from .tree import Tree

class Discard(Exception):
    pass


class Base:
    def _call_userfunc(self, tree):
        return getattr(self, tree.data, self.__default__)(tree)

    def __default__(self, tree):
        "Default operation on tree (for override)"
        return tree

    @classmethod
    def _apply_decorator(cls, decorator):
        mro = getmro(cls)
        assert mro[0] is cls
        libmembers = {name for _cls in mro[1:] for name, _ in getmembers(_cls)}
        for name, value in getmembers(cls):
            if name.startswith('_') or name in libmembers:
                continue

            setattr(cls, name, decorator(value))
        return cls


class SimpleBase(Base):
    def _call_userfunc(self, tree):
        # Assumes tree is already transformed
        try:
            f = getattr(self, tree.data)
        except AttributeError:
            return self.__default__(tree)
        else:
            return f(tree.children)


class Transformer(Base):
    def _transform_children(self, children):
        for c in children:
            try:
                yield self._transform_tree(c) if isinstance(c, Tree) else c
            except Discard:
                pass

    def _transform_tree(self, tree):
        tree = Tree(tree.data, list(self._transform_children(tree.children)))
        return self._call_userfunc(tree)

    def transform(self, tree):
        return self._transform_tree(tree)

    def __mul__(self, other):
        return TransformerChain(self, other)



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
    def _transform_tree(self, tree):           # Cancel recursion
        return self._call_userfunc(tree)

    def transform(self, tree):
        for subtree in tree.iter_subtrees():
            subtree.children = list(self._transform_children(subtree.children))

        return self._transform_tree(tree)


class Transformer_InPlaceRecursive(Transformer):
    def _transform_tree(self, tree):
        tree.children = list(self._transform_children(tree.children))
        return self._call_userfunc(tree)



class Visitor(Base):
    "Bottom-up visitor"

    def visit(self, tree):
        for subtree in tree.iter_subtrees():
            self._call_userfunc(subtree)
        return tree

class Visitor_Recursive(Base):
    def visit(self, tree):
        for child in tree.children:
            if isinstance(child, Tree):
                self.visit(child)

        f = getattr(self, tree.data, self.__default__)
        f(tree)
        return tree


def visit_children_decor(func):
    @wraps(func)
    def inner(cls, tree):
        values = cls.visit_children(tree)
        return func(cls, values)
    return inner

class Interpreter(object):
    "Top-down visitor"

    def visit(self, tree):
        return getattr(self, tree.data)(tree)

    def visit_children(self, tree):
        return [self.visit(child) if isinstance(child, Tree) else child
                for child in tree.children]

    def __getattr__(self, name):
        return self.__default__

    def __default__(self, tree):
        return self.visit_children(tree)





def _apply_decorator(obj, decorator):
    try:
        _apply = obj._apply_decorator
    except AttributeError:
        return decorator(obj)
    else:
        return _apply(decorator)


def _children_args__func(func):
    if getattr(func, '_children_args_decorated', False):
        return func

    @wraps(func)
    def create_decorator(_f, with_self):
        if with_self:
            def f(self, tree):
                return _f(self, tree.children)
        else:
            def f(args):
                return _f(tree.children)
        f._children_args_decorated = True
        return f

    return smart_decorator(func, create_decorator)

def children_args(obj):
    return _apply_decorator(obj, _children_args__func)



def _children_args_inline__func(func):
    if getattr(func, '_children_args_decorated', False):
        return func

    @wraps(func)
    def create_decorator(_f, with_self):
        if with_self:
            def f(self, tree):
                return _f(self, *tree.children)
        else:
            def f(self, tree):
                print ('##', _f, tree)
                return _f(*tree.children)
        f._children_args_decorated = True
        return f

    return smart_decorator(func, create_decorator)


def children_args_inline(obj):
    return _apply_decorator(obj, _children_args_inline__func)
