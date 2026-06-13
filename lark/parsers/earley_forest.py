""""This module implements an SPPF implementation

This is used as the primary output mechanism for the Earley parser
in order to store complex ambiguities.

Full reference and more details is here:
https://web.archive.org/web/20190616123959/http://www.bramvandersanden.com/post/2014/06/shared-packed-parse-forest/
"""

from typing import Type, AbstractSet

from ..utils import OrderedSet


class ForestNode:
    pass

class SymbolNode(ForestNode):
    """
    A Symbol Node represents a symbol (or Intermediate LR0).

    Symbol nodes are keyed by the symbol (s). For intermediate nodes
    s will be an LR0, stored as a tuple of (rule, ptr). For completed symbol
    nodes, s will be a string representing the non-terminal origin (i.e.
    the left hand side of the rule).

    The children of a Symbol or Intermediate Node will always be Packed Nodes;
    with each Packed Node child representing a single derivation of a production.

    Hence a Symbol Node with a single child is unambiguous.

    Parameters:
        s: A Symbol, or a tuple of (rule, ptr) for an intermediate node.
        start: For dynamic lexers, the index of the start of the substring matched by this symbol (inclusive).
        end: For dynamic lexers, the index of the end of the substring matched by this symbol (exclusive).

    Properties:
        is_intermediate: True if this node is an intermediate node.
        priority: The priority of the node's symbol.
    """
    Set: Type[AbstractSet] = set   # Overridden by StableSymbolNode
    __slots__ = ('s', 'start', 'end', '_children', 'paths', 'paths_loaded', 'priority', 'is_intermediate')
    def __init__(self, s, start, end):
        self.s = s
        self.start = start
        self.end = end
        self._children = self.Set()
        self.paths = self.Set()
        self.paths_loaded = False

        ### We use inf here as it can be safely negated without resorting to conditionals,
        #   unlike None or float('NaN'), and sorts appropriately.
        self.priority = float('-inf')
        self.is_intermediate = isinstance(s, tuple)

    def add_family(self, lr0, rule, start, left, right):
        self._children.add(PackedNode(self, lr0, rule, start, left, right))

    def add_path(self, transitive, node):
        self.paths.add((transitive, node))

    def load_paths(self):
        for transitive, node in self.paths:
            if transitive.next_titem is not None:
                vn = type(self)(transitive.next_titem.s, transitive.next_titem.start, self.end)
                vn.add_path(transitive.next_titem, node)
                self.add_family(transitive.reduction.rule.origin, transitive.reduction.rule, transitive.reduction.start, transitive.reduction.node, vn)
            else:
                self.add_family(transitive.reduction.rule.origin, transitive.reduction.rule, transitive.reduction.start, transitive.reduction.node, node)
        self.paths_loaded = True

    @property
    def is_ambiguous(self):
        """Returns True if this node is ambiguous."""
        return len(self.children) > 1

    @property
    def children(self):
        """Returns a list of this node's children sorted from greatest to
        least priority."""
        if not self.paths_loaded:
            self.load_paths()
        from operator import attrgetter
        return sorted(self._children, key=attrgetter('sort_key'))

    def __iter__(self):
        return iter(self._children)

    def __repr__(self):
        if self.is_intermediate:
            rule = self.s[0]
            ptr = self.s[1]
            before = ( expansion.name for expansion in rule.expansion[:ptr] )
            after = ( expansion.name for expansion in rule.expansion[ptr:] )
            symbol = "{} ::= {}* {}".format(rule.origin.name, ' '.join(before), ' '.join(after))
        else:
            symbol = self.s.name
        return "({}, {}, {}, {})".format(symbol, self.start, self.end, self.priority)

class StableSymbolNode(SymbolNode):
    "A version of SymbolNode that uses OrderedSet for output stability"
    Set = OrderedSet

class PackedNode(ForestNode):
    """
    A Packed Node represents a single derivation in a symbol node.

    Parameters:
        rule: The rule associated with this node.
        parent: The parent of this node.
        left: The left child of this node. ``None`` if one does not exist.
        right: The right child of this node. ``None`` if one does not exist.
        priority: The priority of this node.
    """
    __slots__ = ('parent', 's', 'rule', 'start', 'left', 'right', 'priority', '_hash')
    def __init__(self, parent, s, rule, start, left, right):
        self.parent = parent
        self.s = s
        self.start = start
        self.rule = rule
        self.left = left
        self.right = right
        self.priority = float('-inf')
        self._hash = hash((self.left, self.right))

    @property
    def is_empty(self):
        return self.left is None and self.right is None

    @property
    def sort_key(self):
        """
        Used to sort PackedNode children of SymbolNodes.
        A SymbolNode has multiple PackedNodes if it matched
        ambiguously. Hence, we use the sort order to identify
        the order in which ambiguous children should be considered.
        """
        return self.is_empty, -self.priority, self.rule.order

    @property
    def children(self):
        """Returns a list of this node's children."""
        return [x for x in [self.left, self.right] if x is not None]

    def __iter__(self):
        yield self.left
        yield self.right

    def __eq__(self, other):
        if not isinstance(other, PackedNode):
            return False
        return self is other or (self.left == other.left and self.right == other.right)

    def __hash__(self):
        return self._hash

    def __repr__(self):
        if isinstance(self.s, tuple):
            rule = self.s[0]
            ptr = self.s[1]
            before = ( expansion.name for expansion in rule.expansion[:ptr] )
            after = ( expansion.name for expansion in rule.expansion[ptr:] )
            symbol = "{} ::= {}* {}".format(rule.origin.name, ' '.join(before), ' '.join(after))
        else:
            symbol = self.s.name
        return "({}, {}, {}, {})".format(symbol, self.start, self.priority, self.rule.order)

class TokenNode(ForestNode):
    """
    A Token Node represents a matched terminal and is always a leaf node.

    Parameters:
        token: The Token associated with this node.
        term: The TerminalDef matched by the token.
        priority: The priority of this node.
    """
    __slots__ = ('token', 'term', 'priority', '_hash')
    def __init__(self, token, term, priority=None):
        self.token = token
        self.term = term
        if priority is not None:
            self.priority = priority
        else:
            self.priority = term.priority if term is not None else 0
        self._hash = hash(token)

    def __eq__(self, other):
        if not isinstance(other, TokenNode):
            return False
        return self is other or (self.token == other.token)

    def __hash__(self):
        return self._hash

    def __repr__(self):
        return repr(self.token)


# Backward-compatible imports - visitor classes moved to forest_visitors
from .forest_visitors import (
    ForestVisitor, ForestTransformer, ForestSumVisitor,
    ForestToParseTree, TreeForestTransformer, ForestToPyDotVisitor,
    PackedData, handles_ambiguity,
)
