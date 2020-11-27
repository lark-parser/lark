from functools import wraps

from .utils import smart_decorator, combine_alternatives
from .tree import Tree
from .exceptions import VisitError, GrammarError
from .lexer import Token

###{standalone
from inspect import getmembers, getmro


class Discard(Exception):
    """When raising the Discard exception in a transformer callback,
    that node is discarded and won't appear in the parent.
    """
    pass

# Transformers


class _Decoratable:
    "Provides support for decorating methods with @v_args"

    @classmethod
    def _apply_decorator(cls, decorator, **kwargs):
        mro = getmro(cls)
        assert mro[0] is cls
        libmembers = {name for _cls in mro[1:] for name, _ in getmembers(_cls)}
        for name, value in getmembers(cls):

            # Make sure the function isn't inherited (unless it's overwritten)
            if name.startswith('_') or (name in libmembers and name not in cls.__dict__):
                continue
            if not callable(value):
                continue

            # Skip if v_args already applied (at the function level)
            if hasattr(cls.__dict__[name], 'vargs_applied') or hasattr(value, 'vargs_applied'):
                continue

            static = isinstance(cls.__dict__[name], (staticmethod, classmethod))
            setattr(cls, name, decorator(value, static=static, **kwargs))
        return cls

    def __class_getitem__(cls, _):
        return cls


class Transformer(_Decoratable):
    """Transformers visit each node of the tree, and run the appropriate method on it according to the node's data.

    Calls its methods (provided by the user via inheritance) according to ``tree.data``.
    The returned value replaces the old one in the structure.

    They work bottom-up (or depth-first), starting with the leaves and ending at the root of the tree.
    Transformers can be used to implement map & reduce patterns. Because nodes are reduced from leaf to root,
    at any point the callbacks may assume the children have already been transformed (if applicable).

    ``Transformer`` can do anything ``Visitor`` can do, but because it reconstructs the tree,
    it is slightly less efficient. It can be used to implement map or reduce patterns.

    All these classes implement the transformer interface:

    - ``Transformer`` - Recursively transforms the tree. This is the one you probably want.
    - ``Transformer_InPlace`` - Non-recursive. Changes the tree in-place instead of returning new instances
    - ``Transformer_InPlaceRecursive`` - Recursive. Changes the tree in-place instead of returning new instances

    Parameters:
        visit_tokens (bool, optional): Should the transformer visit tokens in addition to rules.
                                       Setting this to ``False`` is slightly faster. Defaults to ``True``.
                                       (For processing ignored tokens, use the ``lexer_callbacks`` options)

    NOTE: A transformer without methods essentially performs a non-memoized deepcopy.
    """
    __visit_tokens__ = True   # For backwards compatibility

    def __init__(self,  visit_tokens=True):
        self.__visit_tokens__ = visit_tokens

    def _call_userfunc(self, tree, new_children=None):
        # Assumes tree is already transformed
        children = new_children if new_children is not None else tree.children
        try:
            f = getattr(self, tree.data)
        except AttributeError:
            return self.__default__(tree.data, children, tree.meta)
        else:
            try:
                wrapper = getattr(f, 'visit_wrapper', None)
                if wrapper is not None:
                    return f.visit_wrapper(f, tree.data, children, tree.meta)
                else:
                    return f(children)
            except (GrammarError, Discard):
                raise
            except Exception as e:
                raise VisitError(tree.data, tree, e)

    def _call_userfunc_token(self, token):
        try:
            f = getattr(self, token.type)
        except AttributeError:
            return self.__default_token__(token)
        else:
            try:
                return f(token)
            except (GrammarError, Discard):
                raise
            except Exception as e:
                raise VisitError(token.type, token, e)

    def _transform_children(self, children):
        for c in children:
            try:
                if isinstance(c, Tree):
                    yield self._transform_tree(c)
                elif self.__visit_tokens__ and isinstance(c, Token):
                    yield self._call_userfunc_token(c)
                else:
                    yield c
            except Discard:
                pass

    def _transform_tree(self, tree):
        children = list(self._transform_children(tree.children))
        return self._call_userfunc(tree, children)

    def transform(self, tree):
        "Transform the given tree, and return the final result"
        return self._transform_tree(tree)

    def __mul__(self, other):
        """Chain two transformers together, returning a new transformer.
        """
        return TransformerChain(self, other)

    def __default__(self, data, children, meta):
        """Default function that is called if there is no attribute matching ``data``

        Can be overridden. Defaults to creating a new copy of the tree node (i.e. ``return Tree(data, children, meta)``)
        """
        return Tree(data, children, meta)

    def __default_token__(self, token):
        """Default function that is called if there is no attribute matching ``token.type``

        Can be overridden. Defaults to returning the token as-is.
        """
        return token


class InlineTransformer(Transformer):   # XXX Deprecated
    def _call_userfunc(self, tree, new_children=None):
        # Assumes tree is already transformed
        children = new_children if new_children is not None else tree.children
        try:
            f = getattr(self, tree.data)
        except AttributeError:
            return self.__default__(tree.data, children, tree.meta)
        else:
            return f(*children)


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
    """Same as Transformer, but non-recursive, and changes the tree in-place instead of returning new instances

    Useful for huge trees. Conservative in memory.
    """
    def _transform_tree(self, tree):           # Cancel recursion
        return self._call_userfunc(tree)

    def transform(self, tree):
        for subtree in tree.iter_subtrees():
            subtree.children = list(self._transform_children(subtree.children))

        return self._transform_tree(tree)


class Transformer_NonRecursive(Transformer):
    """Same as Transformer but non-recursive.

    Like Transformer, it doesn't change the original tree.

    Useful for huge trees.
    """

    def transform(self, tree):
        # Tree to postfix
        rev_postfix = []
        q = [tree]
        while q:
            t = q.pop()
            rev_postfix.append(t)
            if isinstance(t, Tree):
                q += t.children

        # Postfix to tree
        stack = []
        for x in reversed(rev_postfix):
            if isinstance(x, Tree):
                size = len(x.children)
                if size:
                    args = stack[-size:]
                    del stack[-size:]
                else:
                    args = []
                stack.append(self._call_userfunc(x, args))
            else:
                stack.append(x)

        t ,= stack  # We should have only one tree remaining
        return t


class Transformer_InPlaceRecursive(Transformer):
    "Same as Transformer, recursive, but changes the tree in-place instead of returning new instances"
    def _transform_tree(self, tree):
        tree.children = list(self._transform_children(tree.children))
        return self._call_userfunc(tree)


# Visitors

class VisitorBase:
    def _call_userfunc(self, tree):
        return getattr(self, tree.data, self.__default__)(tree)

    def __default__(self, tree):
        """Default function that is called if there is no attribute matching ``tree.data``

        Can be overridden. Defaults to doing nothing.
        """
        return tree

    def __class_getitem__(cls, _):
        return cls


class Visitor(VisitorBase):
    """Tree visitor, non-recursive (can handle huge trees).

    Visiting a node calls its methods (provided by the user via inheritance) according to ``tree.data``
    """

    def visit(self, tree):
        "Visits the tree, starting with the leaves and finally the root (bottom-up)"
        for subtree in tree.iter_subtrees():
            self._call_userfunc(subtree)
        return tree

    def visit_topdown(self,tree):
        "Visit the tree, starting at the root, and ending at the leaves (top-down)"
        for subtree in tree.iter_subtrees_topdown():
            self._call_userfunc(subtree)
        return tree


class Visitor_Recursive(VisitorBase):
    """Bottom-up visitor, recursive.

    Visiting a node calls its methods (provided by the user via inheritance) according to ``tree.data``

    Slightly faster than the non-recursive version.
    """

    def visit(self, tree):
        "Visits the tree, starting with the leaves and finally the root (bottom-up)"
        for child in tree.children:
            if isinstance(child, Tree):
                self.visit(child)

        self._call_userfunc(tree)
        return tree

    def visit_topdown(self,tree):
        "Visit the tree, starting at the root, and ending at the leaves (top-down)"
        self._call_userfunc(tree)

        for child in tree.children:
            if isinstance(child, Tree):
                self.visit_topdown(child)

        return tree


def visit_children_decor(func):
    "See Interpreter"
    @wraps(func)
    def inner(cls, tree):
        values = cls.visit_children(tree)
        return func(cls, values)
    return inner


class Interpreter(_Decoratable):
    """Interpreter walks the tree starting at the root.

    Visits the tree, starting with the root and finally the leaves (top-down)

    For each tree node, it calls its methods (provided by user via inheritance) according to ``tree.data``.

    Unlike ``Transformer`` and ``Visitor``, the Interpreter doesn't automatically visit its sub-branches.
    The user has to explicitly call ``visit``, ``visit_children``, or use the ``@visit_children_decor``.
    This allows the user to implement branching and loops.
    """

    def visit(self, tree):
        f = getattr(self, tree.data)
        wrapper = getattr(f, 'visit_wrapper', None)
        if wrapper is not None:
            return f.visit_wrapper(f, tree.data, tree.children, tree.meta)
        else:
            return f(tree)

    def visit_children(self, tree):
        return [self.visit(child) if isinstance(child, Tree) else child
                for child in tree.children]

    def __getattr__(self, name):
        return self.__default__

    def __default__(self, tree):
        return self.visit_children(tree)


# Decorators

def _apply_decorator(obj, decorator, **kwargs):
    try:
        _apply = obj._apply_decorator
    except AttributeError:
        return decorator(obj, **kwargs)
    else:
        return _apply(decorator, **kwargs)


def _inline_args__func(func):
    @wraps(func)
    def create_decorator(_f, with_self):
        if with_self:
            def f(self, children):
                return _f(self, *children)
        else:
            def f(self, children):
                return _f(*children)
        return f

    return smart_decorator(func, create_decorator)


def inline_args(obj):   # XXX Deprecated
    return _apply_decorator(obj, _inline_args__func)


def _visitor_args_func_dec(func, visit_wrapper=None, static=False):
    def create_decorator(_f, with_self):
        if with_self:
            def f(self, *args, **kwargs):
                return _f(self, *args, **kwargs)
        else:
            def f(self, *args, **kwargs):
                return _f(*args, **kwargs)
        return f

    if static:
        f = wraps(func)(create_decorator(func, False))
    else:
        f = smart_decorator(func, create_decorator)
    f.vargs_applied = True
    f.visit_wrapper = visit_wrapper
    return f


def _vargs_inline(f, _data, children, _meta):
    return f(*children)
def _vargs_meta_inline(f, _data, children, meta):
    return f(meta, *children)
def _vargs_meta(f, _data, children, meta):
    return f(children, meta)   # TODO swap these for consistency? Backwards incompatible!
def _vargs_tree(f, data, children, meta):
    return f(Tree(data, children, meta))


def v_args(inline=False, meta=False, tree=False, wrapper=None):
    """A convenience decorator factory for modifying the behavior of user-supplied visitor methods.

    By default, callback methods of transformers/visitors accept one argument - a list of the node's children.

    ``v_args`` can modify this behavior. When used on a transformer/visitor class definition,
    it applies to all the callback methods inside it.

    ``v_args`` can be applied to a single method, or to an entire class. When applied to both,
    the options given to the method take precedence.

    Parameters:
        inline (bool, optional): Children are provided as ``*args`` instead of a list argument (not recommended for very long lists).
        meta (bool, optional): Provides two arguments: ``children`` and ``meta`` (instead of just the first)
        tree (bool, optional): Provides the entire tree as the argument, instead of the children.
        wrapper (function, optional): Provide a function to decorate all methods.

    Example:
        ::

            @v_args(inline=True)
            class SolveArith(Transformer):
                def add(self, left, right):
                    return left + right


            class ReverseNotation(Transformer_InPlace):
                @v_args(tree=True)
                def tree_node(self, tree):
                    tree.children = tree.children[::-1]
    """
    if tree and (meta or inline):
        raise ValueError("Visitor functions cannot combine 'tree' with 'meta' or 'inline'.")

    func = None
    if meta:
        if inline:
            func = _vargs_meta_inline
        else:
            func = _vargs_meta
    elif inline:
        func = _vargs_inline
    elif tree:
        func = _vargs_tree

    if wrapper is not None:
        if func is not None:
            raise ValueError("Cannot use 'wrapper' along with 'tree', 'meta' or 'inline'.")
        func = wrapper

    def _visitor_args_dec(obj):
        return _apply_decorator(obj, _visitor_args_func_dec, visit_wrapper=func)
    return _visitor_args_dec


###}


# --- Visitor Utilities ---

class CollapseAmbiguities(Transformer):
    """
    Transforms a tree that contains any number of _ambig nodes into a list of trees,
    each one containing an unambiguous tree.

    The length of the resulting list is the product of the length of all _ambig nodes.

    Warning: This may quickly explode for highly ambiguous trees.

    """
    def _ambig(self, options):
        return sum(options, [])

    def __default__(self, data, children_lists, meta):
        return [Tree(data, children, meta) for children in combine_alternatives(children_lists)]

    def __default_token__(self, t):
        return [t]
