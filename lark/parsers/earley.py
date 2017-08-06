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

from functools import cmp_to_key

from ..utils import compare
from ..common import ParseError, UnexpectedToken, Terminal
from ..tree import Tree, Visitor_NoRecurse, Transformer_NoRecurse
from .grammar_analysis import GrammarAnalyzer


class EndToken:
    type = '$end'

class Derivation(Tree):
    def __init__(self, rule, items=None):
        Tree.__init__(self, 'drv', items or [])
        self.rule = rule

    def _pretty_label(self):    # Nicer pretty for debugging the parser
        return self.rule.origin if self.rule else self.data

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
        return Item(self.rule, self.ptr+1, self.start, new_tree)

    def __eq__(self, other):
        return self.start is other.start and self.ptr == other.ptr and self.rule == other.rule
    def __hash__(self):
        return hash((self.rule, self.ptr, id(self.start)))

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
    def __init__(self, i):
        self.i = i
        self.to_reduce = NewsList()
        self.to_predict = NewsList()
        self.to_scan = NewsList()
        self.item_count = 0

        self.added = set()
        self.completed = {}

    def add(self, items):
        """Sort items into scan/predict/reduce newslists

        Makes sure only unique items are added.
        """

        for item in items:

            if item.is_complete:
                # XXX Potential bug: What happens if there's ambiguity in an empty rule?
                if item.rule.expansion and item in self.completed:
                    old_tree = self.completed[item].tree
                    if old_tree.data != '_ambig':
                        new_tree = old_tree.copy()
                        new_tree.rule = old_tree.rule
                        old_tree.set('_ambig', [new_tree])
                        old_tree.rule = None    # No longer a 'drv' node

                    if item.tree.children[0] is old_tree:   # XXX a little hacky!
                        raise ParseError("Infinite recursion in grammar! (Rule %s)" % item.rule)

                    old_tree.children.append(item.tree)
                else:
                    self.completed[item] = item
                self.to_reduce.append(item)
            else:
                if item not in self.added:
                    self.added.add(item)
                    if isinstance(item.expect, Terminal):
                        self.to_scan.append(item)
                    else:
                        self.to_predict.append(item)

            self.item_count += 1    # Only count if actually added

    def __nonzero__(self):
        return bool(self.item_count)

class Parser:
    def __init__(self, rules, start_symbol, callback, resolve_ambiguity=True):
        self.analysis = GrammarAnalyzer(rules, start_symbol)
        self.start_symbol = start_symbol
        self.resolve_ambiguity = resolve_ambiguity

        self.postprocess = {}
        self.predictions = {}
        for rule in self.analysis.rules:
            if rule.origin != '$root':  # XXX kinda ugly
                a = rule.alias
                self.postprocess[rule] = a if callable(a) else (a and getattr(callback, a))
                self.predictions[rule.origin] = [x.rule for x in self.analysis.expand_rule(rule.origin)]

    def parse(self, stream, start_symbol=None):
        # Define parser functions
        start_symbol = start_symbol or self.start_symbol

        def predict(nonterm, column):
            assert not isinstance(nonterm, Terminal), nonterm
            return [Item(rule, 0, column, None) for rule in self.predictions[nonterm]]

        def complete(item):
            name = item.rule.origin
            return [i.advance(item.tree) for i in item.start.to_predict if i.expect == name]

        def predict_and_complete(column):
            while True:
                to_predict = {x.expect for x in column.to_predict.get_news()
                              if x.ptr}  # if not part of an already predicted batch
                to_reduce = column.to_reduce.get_news()
                if not (to_predict or to_reduce):
                    break

                for nonterm in to_predict:
                    column.add( predict(nonterm, column) )
                for item in to_reduce:
                    column.add( complete(item) )

        def scan(i, token, column):
            to_scan = column.to_scan.get_news()

            next_set = Column(i)
            next_set.add(item.advance(token) for item in to_scan if item.expect.match(token))

            if not next_set:
                expect = {i.expect for i in column.to_scan}
                raise UnexpectedToken(token, expect, stream, i)

            return next_set

        # Main loop starts
        column0 = Column(0)
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
            ResolveAmbig().visit(tree) 

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

def _compare_rules(rule1, rule2):
    if rule1.origin != rule2.origin:
        if rule1.options and rule2.options:
            if rule1.options.priority is not None and rule2.options.priority is not None:
                assert rule1.options.priority != rule2.options.priority, "Priority is the same between both rules: %s == %s" % (rule1, rule2)
                return -compare(rule1.options.priority, rule2.options.priority)

        return 0

    c = compare( len(rule1.expansion), len(rule2.expansion))
    if rule1.origin.startswith('__'):   # XXX hack! We need to set priority in parser, not here
        c = -c
    return c

def _compare_drv(tree1, tree2):
    if not (isinstance(tree1, Tree) and isinstance(tree2, Tree)):
        return -compare(tree1, tree2)

    try:
        rule1, rule2 = tree1.rule, tree2.rule
    except AttributeError:
        # Probably trees that don't take part in this parse (better way to distinguish?)
        return -compare(tree1, tree2)

    # XXX These artifacts can appear due to imperfections in the ordering of Visitor_NoRecurse,
    #     when confronted with duplicate (same-id) nodes. Fixing this ordering is possible, but would be
    #     computationally inefficient. So we handle it here.
    if tree1.data == '_ambig':
        _resolve_ambig(tree1)
    if tree2.data == '_ambig':
        _resolve_ambig(tree2)

    c = _compare_rules(tree1.rule, tree2.rule)
    if c:
        return c

    # rules are "equal", so compare trees
    for t1, t2 in zip(tree1.children, tree2.children):
        c = _compare_drv(t1, t2)
        if c:
            return c

    return compare(len(tree1.children), len(tree2.children))


def _resolve_ambig(tree):
    assert tree.data == '_ambig'

    best = min(tree.children, key=cmp_to_key(_compare_drv))
    assert best.data == 'drv'
    tree.set('drv', best.children)
    tree.rule = best.rule   # needed for applying callbacks

    assert tree.data != '_ambig'

class ResolveAmbig(Visitor_NoRecurse):
    def _ambig(self, tree):
        _resolve_ambig(tree)


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
