"This module implements an Earley Parser"

# The parser uses a parse-forest to keep track of derivations and ambiguations.
# When the parse ends successfully, a disambiguation stage resolves all ambiguity
# (right now ambiguity resolution is not developed beyond the needs of lark)
# Afterwards the parse tree is reduced (transformed) according to user callbacks.
# I use the no-recursion version of Transformer, because the tree might be
# deeper than Python's recursion limit (a bit absurd, but that's life)
#
# The algorithm keeps track of each state set, using a corresponding Column instance.
# Column keeps track of new items using NewsList instances.
#
# Author: Erez Shinan (2017)
# Email : erezshin@gmail.com

## for recursive repr
from ..common import is_terminal
from ..tree import Tree

class Derivation(Tree):
    def __init__(self, rule, children=None):
        Tree.__init__(self, 'drv', children if children is not None else [])
        self.rule = rule

    def __repr__(self, indent = 0):
        return 'Derivation(%s, %s, %s)' % (self.data, self.rule.origin, '...')

    def __hash__(self):
        return hash((self.data, tuple(self.children)))

class Item(object):
    "An Earley Item, the atom of the algorithm."

    __slots__ = ('s', 'rule', 'ptr', 'start', 'is_complete', 'expect', 'is_terminal', 'node', '_hash')
    def __init__(self, rule, ptr, start, node = None):
        self.is_complete = len(rule.expansion) == ptr
        self.rule = rule    # rule
        self.ptr = ptr      # ptr
        self.start = start  # j
        self.node = node    # w
        if self.is_complete:
            self.s = rule.origin
            self.expect = None
            self.is_terminal = False
        else:
            self.s = (rule, ptr)
            self.expect = rule.expansion[ptr]
            self.is_terminal = is_terminal(self.expect)
        self._hash = hash((self.s, self.start.i))

    def advance(self):
        return self.__class__(self.rule, self.ptr + 1, self.start, self.node)

    def __eq__(self, other):
        return self is other or (self.s == other.s and self.start.i == other.start.i)

    def __hash__(self):
        return self._hash

    def __repr__(self):
        return '%s (%d)' % (self.s if self.is_complete else self.rule.origin, self.start.i)

class Column:
    "An entry in the table, aka Earley Chart. Contains lists of items."
    def __init__(self, i, FIRST):
        self.i = i
        self.items = set()
        self.FIRST = FIRST

    def add(self, item):
        """Sort items into scan/predict/reduce newslists

        Makes sure only unique items are added.
        """
        self.items.add(item)

    def __bool__(self):
        return bool(self.items)

    __nonzero__ = __bool__  # Py2 backwards-compatibility
