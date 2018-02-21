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
from ..tree import Tree
from .grammar_analysis import GrammarAnalyzer
from .earley_common import Column, Derivation, Item, LR0, TransitiveItem
from .earley_forest import Forest, ForestToTreeVisitor

import collections

class Parser:
    def __init__(self, parser_conf, term_matcher, resolve_ambiguity=None):
        self.analysis = GrammarAnalyzer(parser_conf)
        self.parser_conf = parser_conf
        self.resolve_ambiguity = resolve_ambiguity
        self.forest = None
        self.held_completions = collections.defaultdict(list)

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
        self.forest = Forest()

        def is_quasi_complete(item):
            if not item.s.rule.expansion:
                return True

            quasi = item.advance()
            while not quasi.s.is_complete:
                symbol = quasi.s.expect
                if symbol not in self.NULLABLE:
                    return False

                if quasi.s.rule.origin == start_symbol and symbol == start_symbol:
                    return False
                quasi = quasi.advance()

            return True

        def create_leo_transitives(item, previous, trule, visited):
            if item.s.rule.origin in item.start.transitives:
                previous = item.start.transitives[item.s.rule.origin]
                trule = item.start.transitives[item.s.rule.origin]
                return previous, trule

            is_empty_rule = not self.FIRST[item.s.rule.origin]
            if is_empty_rule:
                return previous, trule

            originator = None
            for key in list(item.start.to_predict):
                if key.s.expect == item.s.rule.origin:
                    if originator is not None:
                        return previous, trule
                    originator = key

            if originator is None:
                return previous, trule

            if originator in visited:
                return previous, trule

            visited.add(originator)
            if not is_quasi_complete(item):
                return previous, trule

            trule = originator.advance()
            if originator.start != item.start:
                visited.clear()

            previous, trule = create_leo_transitives(originator, previous, trule, visited)
            if trule is None:
                return previous, trule

            titem = None
            if previous is not None:
                titem = TransitiveItem(item, trule, originator, previous.column)
                titem.parent = previous
                previous.next_titem = titem
            else:
                titem = TransitiveItem(item, trule, originator, item.start)

            item.start.add(titem)
            return titem, trule

        def predict(nonterm, column):
            assert not is_terminal(nonterm.s.expect), nonterm.s.expect

            expect = nonterm.s.expect
            for rule in self.predictions[expect]:
                lr0 = LR0(rule, 0)
                column.add(Item(lr0, column, None))

            for node in self.held_completions[expect]:
                new_item = nonterm.advance()
                new_item.node = self.forest.make_intermediate_or_symbol_node(new_item.s, nonterm.start, column)
                new_item.node.add_family(new_item.s, new_item.start, nonterm.node, node)
                column.add(new_item)

        def complete_earley(item, column):
            name = item.s.rule.origin
            is_empty_item = item.start.i == column.i
            if is_empty_item:
                self.held_completions[name].append(item.node)

            for originator in list(item.start.to_predict):
                if originator.s.expect == name:
                    new_item = originator.advance()
                    new_item.node = self.forest.make_intermediate_or_symbol_node(new_item.s, originator.start, column)
                    new_item.node.add_family(new_item.s, new_item.start, originator.node, item.node)
                    column.add(new_item)

            # Special case for empty rules; which will always match. 
            # Ensure we continue to advance any items that depend on them.
            is_empty_rule = not self.FIRST[name]
            if is_empty_rule:
                del column.to_reduce[item]

        def complete_leo(item, column):
            transitive = item.start.transitives[item.s.rule.origin]
            if transitive.s.previous in transitive.column.transitives:
                root_transitive = transitive.column.transitives[transitive.s.previous]
            else:
                root_transitive = transitive

            new_node = self.forest.make_virtual_node(column, root_transitive, node)
            new_item = Item(transitive.s, transitive.start, new_node)
            column.add(new_item)

        def complete(item, column):
            if item.node is None:
                item.node = self.forest.make_null_node(item.s, column)

            create_leo_transitives(item, None, None, set([]))
            if item.s.rule.origin in item.start.transitives:
                complete_leo(item, column)
            else:
                complete_earley(item, column)

        def predict_and_complete(column):
            previous_to_predict = set([])
            previous_to_reduce = set([])
            while True:
                completed = [ completion for completion in column.to_reduce if completion not in previous_to_reduce ]
                previous_to_reduce = set(column.to_reduce.keys())

                nonterms = [ prediction for prediction in column.to_predict if prediction not in previous_to_predict and prediction.s.ptr ]
                previous_to_predict = set(column.to_predict.keys())

                if not (completed or nonterms):
                    break

                for nonterm in nonterms:
                    predict(nonterm, column)

                for completion in completed:
                    complete(completion, column)

        def scan(i, token, column):
            next_set = Column(i+1, self.FIRST)
            for item in column.to_scan.values():
                if match(item.s.expect, token):
                    new_item = item.advance()
                    token_node = self.forest.make_token_node(token, item.start, column)
                    new_item.node = self.forest.make_intermediate_or_symbol_node(new_item.s, new_item.start, column)
                    new_item.node.add_family(new_item.s, new_item.start, item.node, token_node)
                    next_set.add(new_item)

            if not next_set:
                expect = {i.s.expect for i in column.to_scan.values()}
                raise UnexpectedToken(token, expect, stream, i)

            return next_set

        # Main loop starts
        column0 = Column(0, self.FIRST)

        ### Predict for the start_symbol
        for rule in self.predictions[start_symbol]:
            lr0 = LR0(rule, 0)
            column0.add(Item(lr0, column0, None))

        column = column0
        for i, token in enumerate(stream):
            self.held_completions.clear()
            predict_and_complete(column)
            column = scan(i, token, column)

        predict_and_complete(column)

        # Parse ended. Now build a parse tree
        solutions = [n.node for n in column.to_reduce 
                  if n.node is not None and n.s.rule.origin==start_symbol and n.start is column0]

        if not solutions:
            raise ParseError('Incomplete parse: Could not find a solution to input')
	elif len(solutions) > 1:
            raise ParseError('Earley should not generate multiple start symbol items!')

        forest_visitor = ForestToTreeVisitor(self.forest, solutions[0])
        tree = forest_visitor.go()

        if self.resolve_ambiguity:
            tree = self.resolve_ambiguity(tree)

        return ApplyCallbacks(self.postprocess).transform(tree)


class ApplyCallbacks(Transformer_NoRecurse):
    def __init__(self, postprocess):
        self.postprocess = postprocess

    def drv(self, tree):
        return self.postprocess[tree.rule](tree.children)
