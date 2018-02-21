"""This module implements an scanerless Earley parser.

The core Earley algorithm used here is based on Elizabeth Scott's implementation, here:
    https://www.sciencedirect.com/science/article/pii/S1571066108001497

That is probably the best reference for understanding the algorithm here.

The Earley parser outputs an SPPF-tree as per that document. The SPPF tree format
is better documented here:
    http://www.bramvandersanden.com/post/2014/06/shared-packed-parse-forest/
"""
# Author: Erez Shinan (2017)
# Email : erezshin@gmail.com

from ..common import ParseError, UnexpectedToken, is_terminal
from ..tree import Transformer_NoRecurse
from .grammar_analysis import GrammarAnalyzer
from .earley_common import Column, Item
from .earley_forest import ForestToTreeVisitor, ForestSumVisitor, SymbolNode, TokenNode, PackedNode

import collections

class Parser:
    def __init__(self, parser_conf, term_matcher, resolve_ambiguity=True, forest_sum_visitor = ForestSumVisitor):
        analysis = GrammarAnalyzer(parser_conf)
        self.parser_conf = parser_conf

        self.FIRST = analysis.FIRST
        self.postprocess = {}
        self.predictions = {}

        self.resolve_ambiguity = resolve_ambiguity
        self.forest_sum_visitor = forest_sum_visitor

        for rule in parser_conf.rules:
            self.postprocess[rule] = rule.alias if callable(rule.alias) else getattr(parser_conf.callback, rule.alias)
            self.predictions[rule.origin] = [x.rule for x in analysis.expand_rule(rule.origin)]

        self.term_matcher = term_matcher


    def parse(self, stream, start_symbol=None):
        # Define parser functions
        start_symbol = start_symbol or self.parser_conf.start
        match = self.term_matcher
        held_completions = collections.defaultdict(list)
        node_cache = {}
        token_cache = {}

        def make_symbol_node(s, start, end):
            label = (s, start.i, end.i)
            if label in node_cache:
                node = node_cache[label]
            else:
                node = node_cache[label] = SymbolNode(s, start, end)
            return node

        def make_packed_node(lr0, rule, start, left, right):
            return PackedNode(lr0, rule, start, left, right)

        def make_token_node(token, start, end):
            label = (token, start.i, end.i)
            if label in token_cache:
                node = token_cache[label]
            else:
                node = token_cache[label] = TokenNode(token, start, end)
            return node

        def predict_and_complete(column, to_scan):
            """The core Earley Predictor and Completer.

            At each stage of the input, we handling any completed items (things
            that matched on the last cycle) and use those to predict what should
            come next in the input stream. The completions and any predicted
            non-terminals are recursively processed until we reach a set of,
            which can be added to the scan list for the next scanner cycle."""
            held_completions.clear()

            # R (items) = Ei (column.items)
            items = list(column.items)
            while items:
                item = items.pop()    # remove an element, A say, from R

                ### The Earley completer
                if item.is_complete:   ### (item.s == string)

                    if item.node is None:
                        item.node = make_symbol_node(item.s, item.start, column)
                        item.node.add_family(make_packed_node(item.s, item.rule, item.start, None, None))

                    # Empty has 0 length. If we complete an empty symbol in a particular
                    # parse step, we need to be able to use that same empty symbol to complete
                    # any predictions that result, that themselves require empty. Avoids
                    # infinite recursion on empty symbols.
                    # held_completions is 'H' in E.Scott's paper.
                    is_empty_item = item.start.i == column.i
                    if is_empty_item:
                        held_completions[item.rule.origin] = item.node

                    originators = [originator for originator in item.start.items if originator.expect == item.s]
                    for originator in originators:
                        new_item = originator.advance()
                        new_item.node = make_symbol_node(new_item.s, originator.start, column)
                        new_item.node.add_family(make_packed_node(new_item.s, new_item.rule, new_item.start, originator.node, item.node))
                        if new_item.is_terminal:
                            # Add (B :: aC.B, h, y) to Q
                            to_scan.add(new_item)
                        elif new_item not in column.items:
                            # Add (B :: aC.B, h, y) to Ei and R
                            column.add(new_item)
                            items.append(new_item)

                ### The Earley predictor
                elif not item.is_terminal: ### (item.s == lr0)
                    new_items = []
                    for rule in self.predictions[item.expect]:
                        new_item = Item(rule, 0, column, None)
                        new_items.append(new_item)

                    # Process any held completions (H).
                    if item.expect in held_completions:
                        new_item = item.advance()
                        new_item.node = make_symbol_node(new_item.s, item.start, column)
                        new_item.node.add_family(make_packed_node(new_item.s, new_item.rule, new_item.start, item.node, held_completions[item.expect]))
                        new_items.append(new_item)

                    for new_item in new_items:
                        if new_item.is_terminal:
                            to_scan.add(new_item)
                        elif new_item not in column.items:
                            column.add(new_item)
                            items.append(new_item)

        def scan(i, token, column, to_scan):
            """The core Earley Scanner.

            This is a custom implementation of the scanner that uses the
            Lark lexer to match tokens. The scan list is built by the
            Earley predictor, based on the previously completed tokens.
            This ensures that at each phase of the parse we have a custom
            lexer context, allowing for more complex ambiguities."""
            next_set = Column(i+1, self.FIRST)
            next_to_scan = set()
            for item in set(to_scan):
                if match(item.expect, token):
                    token_node = make_token_node(token, item.start, next_set)
                    new_item = item.advance()
                    new_item.node = make_symbol_node(new_item.s, new_item.start, column)
                    new_item.node.add_family(make_packed_node(new_item.s, item.rule, new_item.start, item.node, token_node))

                    if new_item.is_terminal:
                        # add (B ::= Aai+1.B, h, y) to Q'
                        next_to_scan.add(new_item)
                    else:
                        # add (B ::= Aa+1.B, h, y) to Ei+1
                        next_set.add(new_item)

            if not next_set and not next_to_scan:
                expect = {i.expect for i in to_scan}
                raise UnexpectedToken(token, expect, stream, i)

            return next_set, next_to_scan

        # Main loop starts
        column0 = Column(0, self.FIRST)
        column = column0

        ## The scan buffer. 'Q' in E.Scott's paper.
        to_scan = set()

        ## Predict for the start_symbol.
        # Add predicted items to the first Earley set (for the predictor) if they
        # result in a non-terminal, or the scanner if they result in a terminal.
        for rule in self.predictions[start_symbol]:
            item = Item(rule, 0, column0, None)
            if item.is_terminal:
                to_scan.add(item)
            else:
                column.add(item)

        ## The main Earley loop.
        # Run the Prediction/Completion cycle for any Items in the current Earley set.
        # Completions will be added to the SPPF tree, and predictions will be recursively
        # processed down to terminals/empty nodes to be added to the scanner for the next
        # step.
        for i, token in enumerate(stream):
            predict_and_complete(column, to_scan)

            # Clear the node_cache and token_cache, which are only relevant for each
            # step in the Earley pass.
            node_cache.clear()
            token_cache.clear()
            column, to_scan = scan(i, token, column, to_scan)

        predict_and_complete(column, to_scan)

        ## Column is now the final column in the parse. If the parse was successful, the start
        # symbol should have been completed in the last step of the Earley cycle, and will be in
        # this column. Find the item for the start_symbol, which is the root of the SPPF tree.
        solutions = [n.node for n in column.items if n.is_complete and n.node is not None and n.s == start_symbol and n.start is column0]

        if not solutions:
            raise ParseError('Incomplete parse: Could not find a solution to input')
        elif len(solutions) > 1:
            raise ParseError('Earley should not generate multiple start symbol items!')

        ## If we're not resolving ambiguity, we just return the root of the SPPF tree to the caller.
        # This means the caller can work directly with the SPPF tree.
        if not self.resolve_ambiguity:
            return solutions[0]

        # ... otherwise, disambiguate and convert the SPPF to an AST, removing any ambiguities
        # according to the rules.
        tree = ForestToTreeVisitor(solutions[0], self.forest_sum_visitor).go()
        return ApplyCallbacks(self.postprocess).transform(tree)

class ApplyCallbacks(Transformer_NoRecurse):
    def __init__(self, postprocess):
        self.postprocess = postprocess

    def drv(self, tree):
        return self.postprocess[tree.rule](tree.children)
