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
from pprint import pformat

from ..common import is_terminal
from ..tree import Tree
import collections

class Derivation(Tree):
    def __init__(self, rule, children=None):
        Tree.__init__(self, 'drv', children if children is not None else [])
        self.rule = rule

    def __repr__(self, indent = 0):
        return 'Derivation(%s, %s, %s)' % (self.data, self.rule.origin, '...')

    def __hash__(self):
        return hash((self.data, tuple(self.children)))

class LR0(object):
    def __init__(self, rule, ptr):
        self.rule = rule
        self.ptr = ptr

    @property
    def expect(self):
        return self.rule.expansion[self.ptr]

    @property
    def previous(self):
        if self.ptr <= 0:
            return None
        return self.rule.expansion[self.ptr - 1]

    @property
    def is_complete(self):
        return self.ptr >= len(self.rule.expansion)

    @property
    def before(self):
        return list(map(str, self.rule.expansion[:self.ptr]))

    @property
    def after(self):
        return list(map(str, self.rule.expansion[self.ptr:]))

    def advance(self):
        assert self.ptr < len(self.rule.expansion), "LR0 being advanced past end of production"
        return self.__class__(self.rule, self.ptr + 1)

    def __eq__(self, other):
        if not isinstance(other, LR0):
            return False
        if self is other:
            return True
        if self.is_complete and other.is_complete:
            return self.rule.origin == other.rule.origin
        return self.rule == other.rule and self.ptr == other.ptr

    def __hash__(self):
        if self.is_complete:
            return hash(self.rule.origin)
        else:
            return hash((hash(self.rule), self.ptr))

    def __repr__(self):
        if self.is_complete:
            return '<%s>' % (self.rule.origin)
        else:
            before = self.before
            after = self.after
            return '<%s -> %s * %s>' % (self.rule.origin, ' '.join(self.before), ' '.join(self.after))

class Item(object):
    "An Earley Item, the atom of the algorithm."

    def __init__(self, s, start, node = None):
        self.s = s          # lr0
        self.start = start  # j
        self.node = node    # w

    def advance(self):
        return self.__class__(self.s.advance(), self.start, self.node)

    @property
    def is_complete(self):
        return self.s.is_complete

    def __eq__(self, other):
        if not isinstance(other, Item):
            return False
        return self is other or (self.s == other.s and self.start.i == other.start.i)

    def __hash__(self):
        return hash((hash(self.s), self.start.i))

    def __repr__(self):
        return '%s (%d)' % (repr(self.s), self.start.i)

class TransitiveItem(Item):

    def __init__(self, recognized, trule, originator, start):
        super(TransitiveItem, self).__init__(trule.s, trule.start)
        self.recognized = recognized 
        self.reduction = originator
        self.column = start
        self.next_titem = None
        self.parent = None

    def __repr__(self):
        before = self.s.before
        after = self.s.after
        return '<(%d) (%d) %s : %s -> %s * %s>' % (id(self), self.start.i, self.recognized.s.rule.origin, self.s.rule.origin, ' '.join(before), ' '.join(after))

class Column:
    "An entry in the table, aka Earley Chart. Contains lists of items."
    def __init__(self, i, FIRST, predict_all=False):
        self.i = i

        ### Need to preserve insertion order for determism of the SPPF tree.
        self.to_reduce = collections.OrderedDict()
        self.to_predict = collections.OrderedDict()
        self.to_scan = collections.OrderedDict()
        self.transitives = collections.OrderedDict()
        self.item_count = 0
        self.FIRST = FIRST

        self.predict_all = predict_all

    def add(self, item):
        """Sort items into scan/predict/reduce newslists

        Makes sure only unique items are added.
        """
        if isinstance(item, TransitiveItem):
            self.transitives.setdefault(item.s.rule.origin, item)
        elif item.is_complete:
            self.to_reduce.setdefault(item, item)
        else:
            if is_terminal(item.s.expect):
                self.to_scan.setdefault(item, item)
            else:
                self.to_predict.setdefault(item, item)

    def __bool__(self):
        return bool(self.to_reduce or self.to_scan or self.to_predict)
    __nonzero__ = __bool__  # Py2 backwards-compatibility
