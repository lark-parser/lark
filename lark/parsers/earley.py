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

#from ..common import ParseError, UnexpectedToken, is_terminal
from ..common import ParseError, UnexpectedToken, is_terminal
from ..tree import Transformer_NoRecurse
#from ..lexer import Token
#from ..grammar import Rule
from .grammar_analysis import GrammarAnalyzer
from .earley_common import Column, Item, LR0
from .earley_forest import Forest, ForestToTreeVisitor

import collections

class Parser:
    def __init__(self, parser_conf, term_matcher, resolve_ambiguity=None):
        self.analysis = GrammarAnalyzer(parser_conf)
        self.parser_conf = parser_conf
        self.resolve_ambiguity = resolve_ambiguity

        self.FIRST = self.analysis.FIRST
        self.NULLABLE = self.analysis.NULLABLE
        self.postprocess = {}
        self.predictions = {}
        for rule in parser_conf.rules:
            self.postprocess[rule] = rule.alias if callable(rule.alias) else getattr(parser_conf.callback, rule.alias)
            self.predictions[rule.origin] = [x.rule for x in self.analysis.expand_rule(rule.origin)]

        self.term_matcher = term_matcher


    def parse(self, stream, start_symbol=None):
        # Define parser functions
        start_symbol = start_symbol or self.parser_conf.start

        _Item = Item
        match = self.term_matcher
        forest = Forest()
        held_completions = collections.defaultdict(list)

        def add(column, items, to_scan, item):
            if item not in column.items:
                column.add(item)
                items.append(item)
            if is_terminal(item.s.expect):
                to_scan.add(item)

        def predict(item, column, items, to_scan):
            for rule in self.predictions[item.s.expect]:
                new_item = Item(LR0(rule, 0), column, None)
                add(column, items, to_scan, new_item)

            for node in held_completions[item.s.expect]:
                new_item = item.advance()
                new_item.node = forest.make_intermediate_or_symbol_node(new_item.s, item.start, column)
                new_item.node.add_family(new_item.s, new_item.start, item.node, node)
                add(column, items, to_scan, new_item)

        def complete(item, column, items, to_scan):
            if item.node is None:
                item.node = forest.make_null_node(item.s, column)

            is_empty_item = item.start.i == column.i
            if is_empty_item:
                held_completions[item.s.rule.origin].append(item.node)

            originators = [ originator for originator in item.start.items if originator.s.expect == item.s.rule.origin ]
            for originator in originators:
                new_item = originator.advance()
                new_item.node = forest.make_intermediate_or_symbol_node(new_item.s, originator.start, column)
                new_item.node.add_family(new_item.s, new_item.start, originator.node, item.node)
                add(column, items, to_scan, new_item)

        def predict_and_complete(column, to_scan):
            held_completions.clear()
            items = list(column.items)
            while items:
                item = items.pop(0)
                if item.is_complete:
                    complete(item, column, items, to_scan)
                elif not is_terminal(item.s.expect):
                    predict(item, column, items, to_scan)

        def scan(i, token, column, to_scan):
            next_set = Column(i+1, self.FIRST)
            next_to_scan = set()
            for item in set(to_scan):
                if match(item.s.expect, token):
                    token_node = forest.make_token_node(token, item.start, next_set)
                    new_item = item.advance()
                    new_item.node = forest.make_intermediate_or_symbol_node(new_item.s, new_item.start, next_set)
                    new_item.node.add_family(new_item.s, new_item.start, item.node, token_node)
                    if new_item not in next_set.items:
                        next_set.add(new_item)
                    if is_terminal(new_item.s.expect):
                        next_to_scan.add(new_item)

            if not next_set and not next_to_scan:
                expect = {i.s.expect for i in to_scan}
                raise UnexpectedToken(token, expect, stream, i)

            return next_set, next_to_scan

        # Main loop starts
        column0 = Column(0, self.FIRST)
        column = column0
        to_scan = set()

        ### Predict for the start_symbol
        for rule in self.predictions[start_symbol]:
            item = Item(LR0(rule, 0), column0, None)
            column.add(item)
            if is_terminal(item.s.expect):
                to_scan.add(item)

        for i, token in enumerate(stream):
            predict_and_complete(column, to_scan)
            column, to_scan = scan(i, token, column, to_scan)

        predict_and_complete(column, to_scan)

        # Parse ended. Now build a parse tree
        solutions = [n.node for n in column.items if n.is_complete and n.node is not None and n.s.rule.origin==start_symbol and n.start is column0]

        if not solutions:
            raise ParseError('Incomplete parse: Could not find a solution to input')
        elif len(solutions) > 1:
            raise ParseError('Earley should not generate multiple start symbol items!')

        forest_visitor = ForestToTreeVisitor(forest, solutions[0])
        tree = forest_visitor.go()

        if self.resolve_ambiguity:
            tree = self.resolve_ambiguity(tree)

        return ApplyCallbacks(self.postprocess).transform(tree)


class ApplyCallbacks(Transformer_NoRecurse):
    def __init__(self, postprocess):
        self.postprocess = postprocess

    def drv(self, tree):
        return self.postprocess[tree.rule](tree.children)
