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

from ..grammar import NonTerminal, Terminal

class Item(object):
    "An Earley Item, the atom of the algorithm."

    __slots__ = ('s', 'rule', 'ptr', 'start', 'is_complete', 'expect', 'previous', 'node', '_hash')
    def __init__(self, rule, ptr, start):
        self.is_complete = len(rule.expansion) == ptr
        self.rule = rule    # rule
        self.ptr = ptr      # ptr
        self.start = start  # j
        self.node = None    # w
        if self.is_complete:
            self.s = rule.origin
            self.expect = None
            self.previous = rule.expansion[ptr - 1] if ptr > 0 and len(rule.expansion) else None
        else:
            self.s = (rule, ptr)
            self.expect = rule.expansion[ptr]
            self.previous = rule.expansion[ptr - 1] if ptr > 0 and len(rule.expansion) else None
        self._hash = hash((self.s, self.start))

    def advance(self):
        return Item(self.rule, self.ptr + 1, self.start)

    def __eq__(self, other):
        return self is other or (self.s == other.s and self.start == other.start)

    def __hash__(self):
        return self._hash

    def __repr__(self):
        before = ( expansion.name for expansion in self.rule.expansion[:self.ptr] )
        after = ( expansion.name for expansion in self.rule.expansion[self.ptr:] )
        symbol = "{} ::= {}* {}".format(self.rule.origin.name, ' '.join(before), ' '.join(after))
        return '%s (%d)' % (symbol, self.start)


class TransitiveItem(Item):
    __slots__ = ('recognized', 'reduction', 'column', 'next_titem')
    def __init__(self, recognized, trule, originator, start):
        super(TransitiveItem, self).__init__(trule.rule, trule.ptr, trule.start)
        self.recognized = recognized
        self.reduction = originator
        self.column = start
        self.next_titem = None
        self._hash = hash((self.s, self.start, self.recognized))

    def __eq__(self, other):
        if not isinstance(other, TransitiveItem):
            return False
        return self is other or (type(self.s) == type(other.s) and self.s == other.s and self.start == other.start and self.recognized == other.recognized)

    def __hash__(self):
        return self._hash

    def __repr__(self):
        before = ( expansion.name for expansion in self.rule.expansion[:self.ptr] )
        after = ( expansion.name for expansion in self.rule.expansion[self.ptr:] )
        return '{} : {} -> {}* {} ({}, {})'.format(self.recognized.name, self.rule.origin.name, ' '.join(before), ' '.join(after), self.column, self.start)
