""""This module implements an SPPF implementation

This is used as the primary output mechanism for the Earley parser
in order to store complex ambiguities.

Full reference and more details is here:
http://www.bramvandersanden.com/post/2014/06/shared-packed-parse-forest/
"""

import collections
import functools
from ..tree import Tree
from ..common import ParseError
from .earley_common import Column, Derivation


class SymbolNode(object):
    """
    A Symbol Node represents a symbol (or Intermediate LR0).

    Symbol nodes are keyed by the symbol (s). For intermediate nodes
    s will be an LR0, stored as a tuple of (rule, ptr). For completed symbol
    nodes, s will be a string representing the non-terminal origin (i.e.
    the left hand side of the rule).

    The children of a Symbol or Intermediate Node will always be Packed Nodes;
    with each Packed Node child representing a single derivation of a production.

    Hence a Symbol Node with a single child is unambiguous.
    """
    __slots__ = ('s', 'start', 'end', 'children', 'priority')
    def __init__(self, s, start, end):
        self.s = s
        self.start = start
        self.end = end

        self.children = set()
        self.priority = None

    def add_family(self, packed_node):
        packed_node.parent = self
        self.children.add(packed_node)

    @property
    def is_ambiguous(self):
        return len(self.children) > 1

    def __eq__(self, other):
        if not isinstance(other, SymbolNode):
            return False
        return self is other or (self.s == other.s and self.start == other.start and self.end is other.end)

    def __hash__(self):
        return hash((self.s, self.start.i, self.end.i))

    def __repr__(self):
        symbol = self.s if isinstance(self.s, basestring) else self.s[0].origin
        return "(%s, %d, %d, %d)" % (symbol, self.start.i, self.end.i, self.priority if self.priority is not None else 0)

@functools.total_ordering
class PackedNode(object):
    """
    A Packed Node represents a single derivation in a symbol node.
    """
    __slots__ = ('parent', 's', 'rule', 'start', 'left', 'right', 'priority')
    def __init__(self, s, rule, start, left, right):
        self.parent = None
        self.s = s
        self.start = start

        self.rule = rule

        self.left = left
        self.right = right
        self.priority = None

    @property
    def is_empty(self):
        return self.left is None and self.right is None

    def __lt__(self, other):
        if self.is_empty and not other.is_empty:
            return True
        if self.priority < other.priority:
            return True
        # if len(self.rule.expansion) < len(other.rule.expansion):
        #     return True
        return False

    def __eq__(self, other):
        if not isinstance(other, PackedNode):
            return False
        return self is other or (self.s == other.s and self.start == other.start and self.left == other.left and self.right == other.right)

    def __hash__(self):
        return hash((hash(self.s), self.start.i, hash(self.left), hash(self.right)))

    def __repr__(self):
        symbol = self.s if isinstance(self.s, basestring) else self.s[0].origin
        return "{%s, %d, %s, %s, %s}" % (symbol, self.start.i, self.left, self.right, self.priority if self.priority is not None else 0)


class TokenNode(object):
    """
    A lightweight node to encapsulate a parse token in the SPPF tree.

    Consider whether we need this long term; of whether we can simply add
    lark Tokens directly to the SPPF tree for performance.
    """
    __slots__ = ('token', 'start', 'end', 'priority')
    def __init__(self, token, start, end):
        self.token = token
        self.start = start
        self.end = end
        self.priority = 0

    def __eq__(self, other):
        if not isinstance(other, TokenNode):
            return False
        return self is other or (self.token == other.token and self.start == other.start and self.end == other.end)

    def __hash__(self):
        return hash((self.token, self.start.i, self.end.i))

    def __repr__(self):
        return "(%s, %s, %s)" % (self.token, self.start.i, self.end.i)

class ForestVisitor(object):
    """
    An abstract base class for building forest visitors.

    Use this as a base when you need to walk the forest.
    """
    def __init__(self, root):
        self.root = root
        self.result = None

    def visit_token_node_in(self, node): pass
    def visit_token_node_out(self, node): pass
    def visit_symbol_node_in(self, node): pass
    def visit_symbol_node_out(self, node): pass
    def visit_packed_node_in(self, node): pass
    def visit_packed_node_out(self, node): pass

    def go(self):
        # Visiting is a list of IDs of all symbol/intermediate nodes currently in
        # the stack. It serves two purposes: to detect when we 'recurse' in and out
        # of a symbol/intermediate so that we can process both up and down. Also,
        # since the SPPF can have cycles it allows us to detect if we're trying
        # to recurse into a node that's already on the stack (infinite recursion).
        visiting = set()

        # We do not use recursion here to walk the Forest due to the limited
        # stack size in python. Therefore input_stack is essentially our stack.
        input_stack = [self.root]
        while input_stack:
            current = next(reversed(input_stack))
            if isinstance(current, collections.Iterator):
                try:
                    next_node = next(current)
                except StopIteration:
                    input_stack.pop()
                else:
                    if next_node is None:
                        continue

                    if id(next_node) in visiting:
                        raise ParseError("Infinite recursion in grammar!")

                    input_stack.append(next_node)
                continue

            current_id = id(current)
            if current_id in visiting:
                if isinstance(current, TokenNode):    self.visit_token_node_out(current)
                elif isinstance(current, SymbolNode): self.visit_symbol_node_out(current)
                else:                                 self.visit_packed_node_out(current)
                input_stack.pop()
                visiting.remove(current_id)
                continue
            else:
                visiting.add(current_id)
                if isinstance(current, TokenNode):    next_node = self.visit_token_node_in(current)
                elif isinstance(current, SymbolNode): next_node = self.visit_symbol_node_in(current)
                else:                                 next_node = self.visit_packed_node_in(current)
                if next_node is None:
                    continue

                if id(next_node) in visiting:
                    raise ParseError("Infinite recursion in grammar!")

                input_stack.append(next_node)
                continue

        return self.result

class ForestSumVisitor(ForestVisitor):
    """
    A visitor for prioritizing ambiguous parts of the Forest.

    This visitor is the default when resolving ambiguity. It pushes the priorities
    from the rules into the SPPF nodes; and then sorts the packed node children
    of ambiguous symbol or intermediate node according to the priorities.
    This relies on the custom sort function provided in PackedNode.__lt__; which
    uses these properties (and other factors) to sort the ambiguous packed nodes.
    """
    def visit_packed_node_in(self, node):
        return iter([node.left, node.right])

    def visit_symbol_node_in(self, node):
        return iter(node.children)

    def visit_packed_node_out(self, node):
        node.priority = 0
        if node.rule.options and node.rule.options.priority:   node.priority += node.rule.options.priority
        if node.right is not None:                             node.priority += node.right.priority
        if node.left is not None:                              node.priority += node.left.priority

    def visit_symbol_node_out(self, node):
        node.priority = max(child.priority for child in node.children)
        node.children = sorted(node.children, reverse = True)

class ForestAntiscoreSumVisitor(ForestSumVisitor):
    """
    A visitor for prioritizing ambiguous parts of the Forest.

    This visitor is used when resolve_ambiguity == 'resolve__antiscore_sum'.
    It pushes the priorities from the rules into the SPPF nodes, and implements
    a 'least cost' mechanism for resolving ambiguity (reverse of the default
    priority mechanism). It uses a custom __lt__ comparator key for sorting
    the packed node children.
    """
    def visit_symbol_node_out(self, node):
        node.priority = min(child.priority for child in node.children)
        node.children = sorted(node.children, key=AntiscoreSumComparator, reverse = True)

@functools.total_ordering
class AntiscoreSumComparator(object):
    __slots__ = ['obj']
    def __init__(self, obj, *args):
        self.obj = obj
    def __lt__(self, other):
        if self.obj.is_empty and not other.obj.is_empty:
            return True
        if self.obj.priority > other.obj.priority:
            return True
        return False

class ForestToTreeVisitor(ForestVisitor):
    """
    A Forest visitor which converts an SPPF forest to an unambiguous AST.

    The implementation in this visitor walks only the first ambiguous child
    of each symbol node. When it finds an ambiguous symbol node it first
    calls the forest_sum_visitor implementation to sort the children
    into preference order using the algorithms defined there; so the first
    child should always be the highest preference. The forest_sum_visitor
    implementation should be another ForestVisitor which sorts the children
    according to some priority mechanism.
    """
    def __init__(self, root, forest_sum_visitor = ForestSumVisitor):
        super(ForestToTreeVisitor, self).__init__(root)
        self.forest_sum_visitor = forest_sum_visitor
        self.output_stack = []
        self.result = None

    def visit_token_node_in(self, node):
        if self.output_stack:
            self.output_stack[-1].children.append(node.token)
        return None

    def visit_symbol_node_in(self, node):
        if node.is_ambiguous and node.priority is None:
            self.forest_sum_visitor(node).go()
        return next(iter(node.children))

    def visit_packed_node_in(self, node):
        if not isinstance(node.parent.s, tuple):
            drv = Derivation(node.rule, [])
            if self.output_stack:
                self.output_stack[-1].children.append(drv)
            self.output_stack.append(drv)
        return iter([node.left, node.right])

    def visit_packed_node_out(self, node):
        if not isinstance(node.parent.s, tuple):
            self.result = self.output_stack.pop()

class ForestToAmbiguousTreeVisitor(ForestVisitor):
    """
    A Forest visitor which converts an SPPF forest to an ambiguous AST.

    Because of the fundamental disparity between what can be stored in
    an SPPF and what can be stored in a Tree; this implementation is not
    complete. It correctly deals with ambiguities that occur on symbol nodes only,
    and cannot deal with ambiguities that occur on intermediate nodes.

    Usually, most parsers can be rewritten to avoid intermediate node
    ambiguities. Also, this implementation could be fixed, however
    the code to handle intermediate node ambiguities is messy and
    would not be performant. It is much better not to use this and
    instead to correctly disambiguate the forest and only store unambiguous
    parses in Trees. It is here just to provide some parity with the
    old ambiguity='explicit'.

    This is mainly used by the test framework, to make it simpler to write
    tests ensuring the SPPF contains the right results.
    """
    def __init__(self, root):
        super(ForestToAmbiguousTreeVisitor, self).__init__(root)
        self.output_stack = []
        self.result = None
#        self.indent = 0
#        self.indent_space = 1

    def visit_token_node_in(self, node):
#        print("{} in: token node: {}".format(self.indent * self.indent_space * ' ', node))
        if self.output_stack:
            self.output_stack[-1].children.append(node.token)
        return None

    def visit_symbol_node_in(self, node):
#        print("{} in: symbol node: {} ambiguity: {}, children: {}, priority: {}".format(self.indent * self.indent_space * ' ', node, node.is_ambiguous, len(node.children), node.priority))
#        self.indent += 1
        if (not isinstance(node.s, tuple)) and node.is_ambiguous:
            ambiguous = Tree('_ambig', [])
            if self.output_stack:
                self.output_stack[-1].children.append(ambiguous)
            self.output_stack.append(ambiguous)
        return iter(node.children)

    def visit_symbol_node_out(self, node):
#        self.indent -= 1
        if node.is_ambiguous:
            self.result = self.output_stack.pop()

    def visit_packed_node_in(self, node):

        #### NOTE:
        ## When an intermediate node (node.parent.s == tuple) has ambiguous children this
        ## forest visitor will break.
        if not isinstance(node.parent.s, tuple):
            drv = Derivation(node.rule, [])
            if self.output_stack:
                self.output_stack[-1].children.append(drv)
            self.output_stack.append(drv)
        return iter([node.left, node.right])

    def visit_packed_node_out(self, node):
        if not isinstance(node.parent.s, tuple):
            self.result = self.output_stack.pop()