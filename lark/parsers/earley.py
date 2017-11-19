"This module implements an Earley Parser"

# The parser uses a parse-forest to keep track of derivations and ambiguations.
# When the parse ends successfully, a disambiguation stage resolves all ambiguity
# (right now ambiguity resolution is not developed beyond the needs of lark)
# Afterwards the parse tree is reduced (transformed) according to user callbacks.
# I use the no-recursion version of Transformer and Visitor, because the tree might be
# deeper than Python's recursion limit (a bit absurd, but that's life)
#
# The algorithm keeps track of each state set, using a corresponding Column instance.
# Column keeps track of new items using NewsList instances.
#
# Author: Erez Shinan (2017)
# Email : erezshin@gmail.com

from ..common import ParseError, UnexpectedToken, Terminal
from ..tree import Tree, Visitor_NoRecurse, Transformer_NoRecurse
from .grammar_analysis import GrammarAnalyzer


class EndToken:
    type = '$end'

class Derivation(Tree):
    _hash = None

    def __init__(self, rule, items=None):
        Tree.__init__(self, 'drv', items or [])
        self.rule = rule

    def _pretty_label(self):    # Nicer pretty for debugging the parser
        return self.rule.origin if self.rule else self.data

    def __hash__(self):
        if self._hash is None:
            self._hash = Tree.__hash__(self)
        return self._hash

END_TOKEN = EndToken()

class Item(object):
    "An Earley Item, the atom of the algorithm."

    def __init__(self, rule, ptr, start, tree):
        self.rule = rule
        self.ptr = ptr
        self.start = start
        self.tree = tree if tree is not None else Derivation(self.rule)

    @property
    def expect(self):
        return self.rule.expansion[self.ptr]

    @property
    def is_complete(self):
        return self.ptr == len(self.rule.expansion)

    def advance(self, tree):
        assert self.tree.data == 'drv'
        new_tree = Derivation(self.rule, self.tree.children + [tree])
        return self.__class__(self.rule, self.ptr+1, self.start, new_tree)

    def similar(self, other):
        return self.start is other.start and self.ptr == other.ptr and self.rule == other.rule

    def __eq__(self, other):
        return self.similar(other) #and (self.tree == other.tree)

    def __hash__(self):
        return hash((self.rule, self.ptr, id(self.start)))   # Always runs Derivation.__hash__

    def __repr__(self):
        before = list(map(str, self.rule.expansion[:self.ptr]))
        after = list(map(str, self.rule.expansion[self.ptr:]))
        return '<(%d) %s : %s * %s>' % (id(self.start), self.rule.origin, ' '.join(before), ' '.join(after))

class NewsList(list):
    "Keeps track of newly added items (append-only)"

    def __init__(self, initial=None):
        list.__init__(self, initial or [])
        self.last_iter = 0

    def get_news(self):
        i = self.last_iter
        self.last_iter = len(self)
        return self[i:]



class Column:
    "An entry in the table, aka Earley Chart. Contains lists of items."
    def __init__(self, i, FIRST):
        self.i = i
        self.to_reduce = NewsList()
        self.to_predict = NewsList()
        self.to_scan = []
        self.item_count = 0
        self.FIRST = FIRST

        self.predicted = set()
        self.completed = {}

    def add(self, items):
        """Sort items into scan/predict/reduce newslists

        Makes sure only unique items are added.
        """
        for item in items:

            if item.is_complete:
                # XXX Potential bug: What happens if there's ambiguity in an empty rule?
                item_key = item, item.tree  # Elsewhere, tree is not part of the comparison
                if item.rule.expansion and item_key in self.completed:
                    old_tree = self.completed[item_key].tree
                    if old_tree == item.tree:
                        is_empty = not self.FIRST[item.rule.origin]
                        if not is_empty:
                            continue

                    if old_tree.data != '_ambig':
                        new_tree = old_tree.copy()
                        new_tree.rule = old_tree.rule
                        old_tree.set('_ambig', [new_tree])
                        old_tree.rule = None    # No longer a 'drv' node

                    if item.tree.children[0] is old_tree:   # XXX a little hacky!
                        raise ParseError("Infinite recursion in grammar! (Rule %s)" % item.rule)

                    if item.tree not in old_tree.children:
                        old_tree.children.append(item.tree)
                    # old_tree.children.append(item.tree)
                else:
                    self.completed[item_key] = item
                self.to_reduce.append(item)
            else:
                if isinstance(item.expect, Terminal):
                    self.to_scan.append(item)
                else:
                    if item in self.predicted:
                        continue
                    self.predicted.add(item)
                    self.to_predict.append(item)

            self.item_count += 1    # Only count if actually added


    def __bool__(self):
        return bool(self.item_count)
    __nonzero__ = __bool__  # Py2 backwards-compatibility

class Parser:
    def __init__(self, rules, start_symbol, callback, resolve_ambiguity=None):
        self.analysis = GrammarAnalyzer(rules, start_symbol)
        self.start_symbol = start_symbol
        self.resolve_ambiguity = resolve_ambiguity

        self.postprocess = {}
        self.predictions = {}
        self.FIRST = {}
        for rule in self.analysis.rules:
            if rule.origin != '$root':  # XXX kinda ugly
                a = rule.alias
                self.postprocess[rule] = a if callable(a) else (a and getattr(callback, a))
                self.predictions[rule.origin] = [x.rule for x in self.analysis.expand_rule(rule.origin)]

                self.FIRST[rule.origin] = self.analysis.FIRST[rule.origin]


    def parse(self, stream, start_symbol=None):
        # Define parser functions
        start_symbol = start_symbol or self.start_symbol

        _Item = Item

        def predict(nonterm, column):
            assert not isinstance(nonterm, Terminal), nonterm
            return [_Item(rule, 0, column, None) for rule in self.predictions[nonterm]]

        def complete(item):
            name = item.rule.origin
            return [i.advance(item.tree) for i in item.start.to_predict if i.expect == name]

        def predict_and_complete(column):
            while True:
                to_predict = {x.expect for x in column.to_predict.get_news()
                              if x.ptr}  # if not part of an already predicted batch
                to_reduce = set(column.to_reduce.get_news())
                if not (to_predict or to_reduce):
                    break

                for nonterm in to_predict:
                    column.add( predict(nonterm, column) )

                for item in to_reduce:
                    new_items = list(complete(item))
                    for new_item in new_items:
                        if new_item.similar(item):
                            raise ParseError('Infinite recursion detected! (rule %s)' % new_item.rule)
                    column.add(new_items)

        def scan(i, token, column):
            next_set = Column(i, self.FIRST)
            next_set.add(item.advance(token) for item in column.to_scan if item.expect.match(token))

            if not next_set:
                expect = {i.expect for i in column.to_scan}
                raise UnexpectedToken(token, expect, stream, i)

            return next_set

        # Main loop starts
        column0 = Column(0, self.FIRST)
        column0.add(predict(start_symbol, column0))

        column = column0
        for i, token in enumerate(stream):
            predict_and_complete(column)
            column = scan(i, token, column)

        predict_and_complete(column)

        # Parse ended. Now build a parse tree
        solutions = [n.tree for n in column.to_reduce
                     if n.rule.origin==start_symbol and n.start is column0]

        if not solutions:
            raise ParseError('Incomplete parse: Could not find a solution to input')
        elif len(solutions) == 1:
            tree = solutions[0]
        else:
            tree = Tree('_ambig', solutions)

        if self.resolve_ambiguity:
            tree = self.resolve_ambiguity(tree)

        return ApplyCallbacks(self.postprocess).transform(tree)


class ApplyCallbacks(Transformer_NoRecurse):
    def __init__(self, postprocess):
        self.postprocess = postprocess

    def drv(self, tree):
        children = tree.children
        callback = self.postprocess[tree.rule]
        if callback:
            return callback(children)
        else:
            return Tree(rule.origin, children)

# RULES = [
#     ('a', ['d']),
#     ('d', ['b']),
#     ('b', ['C']),
#     ('b', ['b', 'C']),
#     ('b', ['C', 'b']),
# ]
# p = Parser(RULES, 'a')
# for x in p.parse('CC'):
#     print x.pretty()

#---------------
# RULES = [
#     ('s', ['a', 'a']),
#     ('a', ['b', 'b']),
#     ('b', ['C'], lambda (x,): x),
#     ('b', ['b', 'C']),
# ]
# p = Parser(RULES, 's', {})
# print p.parse('CCCCC').pretty()
