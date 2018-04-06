try:
    from future_builtins import filter
except ImportError:
    pass

from collections import deque
from copy import deepcopy

from .utils import inline_args

###{standalone
class Tree(object):
    __slots__ = ('data', 'children', 'tags')

    def __init__(self, data, children, tags=None):
        self.data = data
        self.children = children
        self.tags = tags

    def __repr__(self):
        return 'Tree(%s, %s)' % (self.data, self.children)

    def __iter__(self):
        return iter(self.children)

    def __len__(self):
        return len(self.children)

    def __hasitem__(self, tag):
        return self.tags and tag in self.tags

    def __getitem__(self, tag):
        if self.tags is None:
            raise KeyError(tag)
        return self.tags[tag]

    def __setitem__(self, tag, value):
        if self.tags is None:
            self.tags = {}
        self.tags[tag] = value

    def __getstate__(self):
        return {
            'data': self.data,
            'children': self.children,
            'tags': self.tags
        }

    def __setstate__(self, state):
        self.data = state['data']
        self.children = state['children']
        self.tags = state['tags']

    def _pretty_label(self):
        return self.data

    def _pretty(self, level, indent_str):
        if len(self.children) == 1 and not isinstance(self.children[0], Tree):
            return [ indent_str*level, self._pretty_label(), '\t', '%s' % (self.children[0],), '\n']

        l = [ indent_str*level, self._pretty_label(), '\n' ]
        for n in self.children:
            if isinstance(n, Tree):
                l += n._pretty(level+1, indent_str)
            else:
                l += [ indent_str*(level+1), '%s' % (n,), '\n' ]

        return l

    def pretty(self, indent_str='  '):
        return ''.join(self._pretty(0, indent_str))
###}

    def expand_kids_by_index(self, *indices):
        for i in sorted(indices, reverse=True): # reverse so that changing tail won't affect indices
            kid = self.children[i]
            self.children[i:i+1] = kid.children

    def __eq__(self, other):
        try:
            return self.data == other.data and self.children == other.children
        except AttributeError:
            return False

    def __ne__(self, other):
        return not (self == other)

    def __hash__(self):
        return hash((self.data, tuple(self.children)))

    def find_pred(self, pred):
        return filter(pred, self.iter_subtrees())

    def find_data(self, data):
        return self.find_pred(lambda t: t.data == data)

    def scan_values(self, pred):
        for c in self.children:
            if isinstance(c, Tree):
                for t in c.scan_values(pred):
                    yield t
            else:
                if pred(c):
                    yield c

    def iter_subtrees(self):
        # TODO: Re-write as a more efficient version

        visited = set()
        q = deque()
        q.append(self)

        l = deque()
        while q:
            subtree = q.pop()
            l.appendleft(subtree)
            id_ = id(subtree)
            if id_ in visited:
                continue    # already been here from another branch
            visited.add(id_)
            q.extend(c for c in subtree.children if isinstance(c, Tree))

        seen = set()
        for x in l:
            id_ = id(x)
            if id_ not in seen:
                yield x
                seen.add(id_)

    def __copy__(self):
        cls = self.__class__
        new = cls.__new__(cls)

        tags = self.tags.copy() if self.tags else None
        Tree.__init__(new, self.data, self.children, tags)

        if hasattr(new, '__dict__'):
            new.__dict__.update(self.__dict__)

        return new

    def __deepcopy__(self, memo):
        new = self.__copy__()
        memo[id(self)] = new
        new.children = deepcopy(self.children, memo)
        new.tags = deepcopy(self.tags, memo)

        if hasattr(new, '__dict__'):
            new.__dict__ = deepcopy(self.__dict__, memo)

        return new

    def copy(self):
        return self.__copy__()

    def set(self, data, children):
        self.data = data
        self.children = children



###{standalone
class Transformer(object):
    def _get_func(self, name):
        return getattr(self, name, None)

    def transform(self, tree):
        items = []
        for c in tree.children:
            try:
                items.append(self.transform(c) if isinstance(c, Tree) else c)
            except Discard:
                pass

        f = self._get_func(tree.data)
        if f is None:
            return self.__default__(tree.data, items, tree)
        else:
            return f(items)

    def __default__(self, name, items, original=None):
        if original:
            tree = original.copy()
            tree.set(name, items)
        else:
            tree = Tree(name, items)
        return tree

    def __mul__(self, other):
        return TransformerChain(self, other)


class Discard(Exception):
    pass

class TransformerChain(object):
    def __init__(self, *transformers):
        self.transformers = transformers

    def transform(self, tree):
        for t in self.transformers:
            tree = t.transform(tree)
        return tree

    def __mul__(self, other):
        return TransformerChain(*self.transformers + (other,))



class InlineTransformer(Transformer):
    def _get_func(self, name):
        f = super(InlineTransformer, self)._get_func(name)
        if f is None:
            return None
        return inline_args(f).__get__(self)


class Visitor(object):
    def visit(self, tree):
        recurse = self.visit
        for child in tree.children:
            if isinstance(child, Tree):
                recurse(child)

        f = getattr(self, tree.data, self.__default__)
        f(tree)
        return tree

    def __default__(self, tree):
        pass


class Visitor_NoRecurse(Visitor):
    def visit(self, tree):
        subtrees = list(tree.iter_subtrees())

        for subtree in subtrees:
            getattr(self, subtree.data, self.__default__)(subtree)

        return tree


class Transformer_NoRecurse(Transformer):
    def transform(self, tree):
        # TODO: why materialize the iterator?
        subtrees = list(tree.iter_subtrees())

        def _t(t):
            # Assumes t is already transformed
            f = self._get_func(t.data)
            if f is None:
                return self.__default__(t)
            else:
                return f(t)

        for subtree in subtrees:
            children = []
            for c in subtree.children:
                try:
                    children.append(_t(c) if isinstance(c, Tree) else c)
                except Discard:
                    pass
            subtree.children = children

        return _t(tree)

    def __default__(self, t):
        return t
###}


def pydot__tree_to_png(tree, filename):
    import pydot
    graph = pydot.Dot(graph_type='digraph', rankdir="LR")

    i = [0]

    def new_leaf(leaf):
        node = pydot.Node(i[0], label=repr(leaf))
        i[0] += 1
        graph.add_node(node)
        return node

    def _to_pydot(subtree):
        color = hash(subtree.data) & 0xffffff
        color |= 0x808080

        subnodes = [_to_pydot(child) if isinstance(child, Tree) else new_leaf(child)
                    for child in subtree.children]
        node = pydot.Node(i[0], style="filled", fillcolor="#%x"%color, label=subtree.data)
        i[0] += 1
        graph.add_node(node)

        for subnode in subnodes:
            graph.add_edge(pydot.Edge(node, subnode))

        return node

    _to_pydot(tree)
    graph.write_png(filename)

