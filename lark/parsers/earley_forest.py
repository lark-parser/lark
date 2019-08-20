""""This module implements an SPPF implementation

This is used as the primary output mechanism for the Earley parser
in order to store complex ambiguities.

Full reference and more details is here:
http://www.bramvandersanden.com/post/2014/06/shared-packed-parse-forest/
"""

from random import randint
from math import isinf
from collections import deque
from operator import attrgetter
from importlib import import_module

from ..tree import Tree
from ..exceptions import ParseError

class ForestNode(object):
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
    """
    __slots__ = ('s', 'start', 'end', '_children', 'paths', 'paths_loaded', 'priority', 'is_intermediate', '_hash')
    def __init__(self, s, start, end):
        self.s = s
        self.start = start
        self.end = end
        self._children = set()
        self.paths = set()
        self.paths_loaded = False

        ### We use inf here as it can be safely negated without resorting to conditionals,
        #   unlike None or float('NaN'), and sorts appropriately.
        self.priority = float('-inf')
        self.is_intermediate = isinstance(s, tuple)
        self._hash = hash((self.s, self.start, self.end))

    def add_family(self, lr0, rule, start, left, right):
        self._children.add(PackedNode(self, lr0, rule, start, left, right))

    def add_path(self, transitive, node):
        self.paths.add((transitive, node))

    def load_paths(self):
        for transitive, node in self.paths:
            if transitive.next_titem is not None:
                vn = SymbolNode(transitive.next_titem.s, transitive.next_titem.start, self.end)
                vn.add_path(transitive.next_titem, node)
                self.add_family(transitive.reduction.rule.origin, transitive.reduction.rule, transitive.reduction.start, transitive.reduction.node, vn)
            else:
                self.add_family(transitive.reduction.rule.origin, transitive.reduction.rule, transitive.reduction.start, transitive.reduction.node, node)
        self.paths_loaded = True

    @property
    def is_ambiguous(self):
        return len(self.children) > 1

    @property
    def children(self):
        if not self.paths_loaded: self.load_paths()
        return sorted(self._children, key=attrgetter('sort_key'))

    def __iter__(self):
        return iter(self._children)

    def __eq__(self, other):
        if not isinstance(other, SymbolNode):
            return False
        return self is other or (type(self.s) == type(other.s) and self.s == other.s and self.start == other.start and self.end is other.end)

    def __hash__(self):
        return self._hash

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

class PackedNode(ForestNode):
    """
    A Packed Node represents a single derivation in a symbol node.
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

    def __iter__(self):
        return iter([self.left, self.right])

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

class ForestVisitor(object):
    """
    An abstract base class for building forest visitors.

    Use this as a base when you need to walk the forest.
    """
    __slots__ = ['result']

    def visit_token_node(self, node): pass
    def visit_symbol_node_in(self, node): pass
    def visit_symbol_node_out(self, node): pass
    def visit_packed_node_in(self, node): pass
    def visit_packed_node_out(self, node): pass

    def visit(self, root):
        self.result = None
        # Visiting is a list of IDs of all symbol/intermediate nodes currently in
        # the stack. It serves two purposes: to detect when we 'recurse' in and out
        # of a symbol/intermediate so that we can process both up and down. Also,
        # since the SPPF can have cycles it allows us to detect if we're trying
        # to recurse into a node that's already on the stack (infinite recursion).
        visiting = set()

        # We do not use recursion here to walk the Forest due to the limited
        # stack size in python. Therefore input_stack is essentially our stack.
        input_stack = deque([root])

        # It is much faster to cache these as locals since they are called
        # many times in large parses.
        vpno = getattr(self, 'visit_packed_node_out')
        vpni = getattr(self, 'visit_packed_node_in')
        vsno = getattr(self, 'visit_symbol_node_out')
        vsni = getattr(self, 'visit_symbol_node_in')
        vtn = getattr(self, 'visit_token_node')
        while input_stack:
            current = next(reversed(input_stack))
            try:
                next_node = next(current)
            except StopIteration:
                input_stack.pop()
                continue
            except TypeError:
                ### If the current object is not an iterator, pass through to Token/SymbolNode
                pass
            else:
                if next_node is None:
                    continue

                if id(next_node) in visiting:
                    raise ParseError("Infinite recursion in grammar!")

                input_stack.append(next_node)
                continue

            if not isinstance(current, ForestNode):
                vtn(current)
                input_stack.pop()
                continue

            current_id = id(current)
            if current_id in visiting:
                if isinstance(current, PackedNode):    vpno(current)
                else:                                  vsno(current)
                input_stack.pop()
                visiting.remove(current_id)
                continue
            else:
                visiting.add(current_id)
                if isinstance(current, PackedNode): next_node = vpni(current)
                else:                               next_node = vsni(current)
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

    This visitor is used when support for explicit priorities on
    rules is requested (whether normal, or invert). It walks the
    forest (or subsets thereof) and cascades properties upwards
    from the leaves.

    It would be ideal to do this during parsing, however this would
    require processing each Earley item multiple times. That's
    a big performance drawback; so running a forest walk is the
    lesser of two evils: there can be significantly more Earley
    items created during parsing than there are SPPF nodes in the
    final tree.
    """
    def visit_packed_node_in(self, node):
        return iter([node.left, node.right])

    def visit_symbol_node_in(self, node):
        return iter(node.children)

    def visit_packed_node_out(self, node):
        priority = node.rule.options.priority if not node.parent.is_intermediate and node.rule.options and node.rule.options.priority else 0
        priority += getattr(node.right, 'priority', 0)
        priority += getattr(node.left, 'priority', 0)
        node.priority = priority

    def visit_symbol_node_out(self, node):
        node.priority = max(child.priority for child in node.children)

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
    __slots__ = ['forest_sum_visitor', 'callbacks', 'output_stack']
    def __init__(self, callbacks, forest_sum_visitor = None):
        assert callbacks
        self.forest_sum_visitor = forest_sum_visitor
        self.callbacks = callbacks

    def visit(self, root):
        self.output_stack = deque()
        return super(ForestToTreeVisitor, self).visit(root)

    def visit_token_node(self, node):
        self.output_stack[-1].append(node)

    def visit_symbol_node_in(self, node):
        if self.forest_sum_visitor and node.is_ambiguous and isinf(node.priority):
            self.forest_sum_visitor.visit(node)
        return next(iter(node.children))

    def visit_packed_node_in(self, node):
        if not node.parent.is_intermediate:
            self.output_stack.append([])
        return iter([node.left, node.right])

    def visit_packed_node_out(self, node):
        if not node.parent.is_intermediate:
            result = self.callbacks[node.rule](self.output_stack.pop())
            if self.output_stack:
                self.output_stack[-1].append(result)
            else:
                self.result = result

class ForestToAmbiguousTreeVisitor(ForestToTreeVisitor):
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
    def __init__(self, callbacks, forest_sum_visitor = ForestSumVisitor):
        super(ForestToAmbiguousTreeVisitor, self).__init__(callbacks, forest_sum_visitor)

    def visit_token_node(self, node):
        self.output_stack[-1].children.append(node)

    def visit_symbol_node_in(self, node):
        if self.forest_sum_visitor and node.is_ambiguous and isinf(node.priority):
            self.forest_sum_visitor.visit(node)
        if not node.is_intermediate and node.is_ambiguous:
            self.output_stack.append(Tree('_ambig', []))
        return iter(node.children)

    def visit_symbol_node_out(self, node):
        if not node.is_intermediate and node.is_ambiguous:
            result = self.output_stack.pop()
            if self.output_stack:
                self.output_stack[-1].children.append(result)
            else:
                self.result = result

    def visit_packed_node_in(self, node):
        if not node.parent.is_intermediate:
            self.output_stack.append(Tree('drv', []))
        return iter([node.left, node.right])

    def visit_packed_node_out(self, node):
        if not node.parent.is_intermediate:
            result = self.callbacks[node.rule](self.output_stack.pop().children)
            if self.output_stack:
                self.output_stack[-1].children.append(result)
            else:
                self.result = result

class ForestToPyDotVisitor(ForestVisitor):
    """
    A Forest visitor which writes the SPPF to a PNG.

    The SPPF can get really large, really quickly because
    of the amount of meta-data it stores, so this is probably
    only useful for trivial trees and learning how the SPPF
    is structured.
    """
    def __init__(self, rankdir="TB"):
        self.pydot = import_module('pydot')
        self.graph = self.pydot.Dot(graph_type='digraph', rankdir=rankdir)

    def visit(self, root, filename):
        super(ForestToPyDotVisitor, self).visit(root)
        self.graph.write_png(filename)

    def visit_token_node(self, node):
        graph_node_id = str(id(node))
        graph_node_label = "\"{}\"".format(node.value.replace('"', '\\"'))
        graph_node_color = 0x808080
        graph_node_style = "\"filled,rounded\""
        graph_node_shape = "diamond"
        graph_node = self.pydot.Node(graph_node_id, style=graph_node_style, fillcolor="#{:06x}".format(graph_node_color), shape=graph_node_shape, label=graph_node_label)
        self.graph.add_node(graph_node)

    def visit_packed_node_in(self, node):
        graph_node_id = str(id(node))
        graph_node_label = repr(node)
        graph_node_color = 0x808080
        graph_node_style = "filled"
        graph_node_shape = "diamond"
        graph_node = self.pydot.Node(graph_node_id, style=graph_node_style, fillcolor="#{:06x}".format(graph_node_color), shape=graph_node_shape, label=graph_node_label)
        self.graph.add_node(graph_node)
        return iter([node.left, node.right])

    def visit_packed_node_out(self, node):
        graph_node_id = str(id(node))
        graph_node = self.graph.get_node(graph_node_id)[0]
        for child in [node.left, node.right]:
            if child is not None:
                child_graph_node_id = str(id(child))
                child_graph_node = self.graph.get_node(child_graph_node_id)[0]
                self.graph.add_edge(self.pydot.Edge(graph_node, child_graph_node))
            else:
                #### Try and be above the Python object ID range; probably impl. specific, but maybe this is okay.
                child_graph_node_id = str(randint(100000000000000000000000000000,123456789012345678901234567890))
                child_graph_node_style = "invis"
                child_graph_node = self.pydot.Node(child_graph_node_id, style=child_graph_node_style, label="None")
                child_edge_style = "invis"
                self.graph.add_node(child_graph_node)
                self.graph.add_edge(self.pydot.Edge(graph_node, child_graph_node, style=child_edge_style))

    def visit_symbol_node_in(self, node):
        graph_node_id = str(id(node))
        graph_node_label = repr(node)
        graph_node_color = 0x808080
        graph_node_style = "\"filled\""
        if node.is_intermediate:
            graph_node_shape = "ellipse"
        else:
            graph_node_shape = "rectangle"
        graph_node = self.pydot.Node(graph_node_id, style=graph_node_style, fillcolor="#{:06x}".format(graph_node_color), shape=graph_node_shape, label=graph_node_label)
        self.graph.add_node(graph_node)
        return iter(node.children)

    def visit_symbol_node_out(self, node):
        graph_node_id = str(id(node))
        graph_node = self.graph.get_node(graph_node_id)[0]
        for child in node.children:
            child_graph_node_id = str(id(child))
            child_graph_node = self.graph.get_node(child_graph_node_id)[0]
            self.graph.add_edge(self.pydot.Edge(graph_node, child_graph_node))
