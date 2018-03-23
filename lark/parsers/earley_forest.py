from ..lexer import Token
from ..tree import Tree
from ..utils import convert_camelcase
from ..common import ParseError
from .earley_common import Column, Derivation, LR0
from collections import Iterator

class PackedNode(object):
    def __init__(self, parent, s, start, left, right):
        assert isinstance(parent, (SymbolNode, IntermediateNode))
        assert isinstance(s, LR0)
        assert isinstance(start, Column)
        assert isinstance(left, (TokenNode, SymbolNode, IntermediateNode)) or left is None
        assert isinstance(right, (TokenNode, SymbolNode, IntermediateNode)) or right is None
        self.parent = parent
        self.s = s
        self.start = start
        self.left = left
        self.right = right
        self.priority = 0

    def __eq__(self, other):
        if not isinstance(other, PackedNode):
            return False
        return self is other or (self.s == other.s and self.start == other.start and self.left == other.left and self.right == other.right)

    def __hash__(self):
        return hash((hash(self.s), self.start.i, hash(self.left), hash(self.right)))

    def __repr__(self):
        return "{%s, %d, %s, %s}" % (self.s, self.start.i, self.left, self.right)

class IntermediateNode(object):
    def __init__(self, s, start, end):
        assert isinstance(s, LR0)
        assert isinstance(start, Column)
        assert isinstance(end, Column)
        self.s = s
        self.start = start
        self.end = end
        self.children = None
        self.priority = 0

    def add_family(self, lr0, start, left, right):
        packed_node = PackedNode(self, lr0, start, left, right)
        if self.children is None:
            self.children = [ packed_node ]
        if packed_node not in self.children:
            self.children.append(packed_node)

    @property
    def is_ambiguous(self):
        return len(self.children) > 1

    def __eq__(self, other):
        if not isinstance(other, IntermediateNode):
            return False
        return self is other or (self.s == other.s and self.start == other.start and self.end == other.end)

    def __hash__(self):
        return hash((hash(self.s), self.start.i, self.end.i))

    def __repr__(self):
        return "[%s, %d, %d]" % (self.s, self.start.i, self.end.i)

class SymbolNode(object):
    def __init__(self, s, start, end):
        assert isinstance(s, LR0)
        assert isinstance(start, Column)
        assert isinstance(end, Column)
        self.s = s
        self.start = start
        self.end = end
        self.children = None
        self.priority = 0

    def add_family(self, lr0, start, left, right):
        # Note which production is responsible for this subtree,
        # to help navigate the tree in case of ambiguity
        packed_node = PackedNode(self, lr0, start, left, right)
        if self.children is None:
            self.children = [ packed_node ]
        if packed_node not in self.children:
            self.children.append(packed_node)

    @property
    def is_ambiguous(self):
        return len(self.children) > 1

    def __eq__(self, other):
        if not isinstance(other, SymbolNode):
            return False
        return self is other or (self.s == other.s and self.start == other.start and self.end == other.end)

    def __hash__(self):
        return hash((hash(self.s), self.start.i, self.end.i))

    def __repr__(self):
        return "(%s, %d, %d)" % (self.s.rule.origin, self.start.i, self.end.i)


class TokenNode(object):
    def __init__(self, token, start, end):
        assert isinstance(token, Token)
        assert isinstance(start, Column)
        assert isinstance(end, Column)
        self.token = token
        self.start = start
        self.end = end

    def __eq__(self, other):
        if not isinstance(other, TokenNode):
            return False
        return self is other or (self.token == other.token and self.start == other.start and self.end == other.end)

    def __hash__(self):
        return hash((self.token, self.start.i, self.end.i))

    def __repr__(self):
        return "(%s, %s, %s)" % (self.token, self.start.i, self.end.i)

class Forest(object):
    def __init__(self):
        self.node_cache = {}
        self.token_cache = {}

    def reset(self):
        pass

    def make_intermediate_or_symbol_node(self, lr0, start, end):
        assert isinstance(lr0, LR0)
        assert isinstance(start, Column)
        assert isinstance(end, Column)
        if lr0.is_complete:
            label = (lr0.rule.origin, start.i, end.i)
            node = self.node_cache.setdefault(label, SymbolNode(lr0, start, end))
        else:
            label = (lr0, start.i, end.i)
            node = self.node_cache.setdefault(label, IntermediateNode(lr0, start, end))
        return node

    def make_token_node(self, token, start, end):
        assert isinstance(token, Token)
        assert isinstance(start, Column)
        assert isinstance(end, Column)
        label = (token, start.i, end.i)
        return self.token_cache.setdefault(label, TokenNode(token, start, end))

    def make_null_node(self, lr0, column):
        assert isinstance(lr0, LR0)
        assert isinstance(column, Column)
        if lr0.is_complete:
            label = (lr0.rule.origin, column.i, column.i)
            node = self.node_cache.setdefault(label, SymbolNode(lr0, column, column))
        else:
            label = (lr0, column.i, column.i)
            node = self.node_cache.setdefault(label, IntermediateNode(lr0, column, column))
        node.add_family(lr0, column, None, None)
        return node

class ForestVisitor(object):
    def __init__(self, forest, root):
        self.forest = forest
        self.root = root

    def go(self):
        visiting = set([])
        input_stack = [self.root]
        while input_stack:
            current = next(reversed(input_stack))

            if isinstance(current, Iterator):
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
            elif current == None:
                input_stack.pop()
                continue

            function_name = "visit_" + convert_camelcase(current.__class__.__name__)
            if id(current) in visiting:
                function_name += "_out"
            else:
                function_name += "_in"

            f = None
            try:
                f = getattr(self, function_name)
            except AttributeError:
                pass

            if id(current) in visiting:
                if f:
                    f(current)
                input_stack.pop()
                visiting.remove(id(current))
                continue
            else:
                visiting.add(id(current))
                if f:
                    next_node = f(current)
                    if next_node is None:
                        continue

                    if id(next_node) in visiting:
                        raise ParseError("Infinite recursion in grammar!")

                    input_stack.append(next_node)
                continue

        return self.result

class ForestToTreeVisitor(ForestVisitor):
    def __init__(self, forest, root):
        super(ForestToTreeVisitor, self).__init__(forest, root)
        self.output_stack = []
        self.result = None

    def visit_token_node_in(self, node):
        if self.output_stack:
            self.output_stack[-1].children.append(node.token)
        return None

    def visit_symbol_node_in(self, node):
        if node.is_ambiguous:
            ambiguous = Tree('_ambig', [])
            if self.output_stack:
                self.output_stack[-1].children.append(ambiguous)
            self.output_stack.append(ambiguous)
        else:
            drv = Derivation(node.s.rule, [])
            if self.output_stack:
                self.output_stack[-1].children.append(drv)
            self.output_stack.append(drv)
        return iter(node.children)

    def visit_symbol_node_out(self, node):
        self.result = self.output_stack.pop()

    def visit_intermediate_node_in(self, node):
        return iter(node.children)

    def visit_packed_node_in(self, node):
        if node.parent.is_ambiguous:
            drv = Derivation(node.s.rule, [])
            if self.output_stack:
                if isinstance(node.parent, SymbolNode):
                    self.output_stack[-1].children.append(drv)
                ### Special case: ambiguous intermediates should layer their derivation under the parent's _ambig, not the parent drv
                else:
                    self.output_stack[-2].children.append(drv)
            self.output_stack.append(drv)
        return iter([node.left, node.right])

    def visit_packed_node_out(self, node):
        if node.parent.is_ambiguous:
            drv = self.output_stack.pop()
            drv.priority = node.priority
