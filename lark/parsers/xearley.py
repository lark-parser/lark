"""This module implements an experimental Earley parser with a dynamic lexer

The core Earley algorithm used here is based on Elizabeth Scott's implementation, here:
    https://www.sciencedirect.com/science/article/pii/S1571066108001497

That is probably the best reference for understanding the algorithm here.

The Earley parser outputs an SPPF-tree as per that document. The SPPF tree format
is better documented here:
    http://www.bramvandersanden.com/post/2014/06/shared-packed-parse-forest/

Instead of running a lexer beforehand, or using a costy char-by-char method, this parser
uses regular expressions by necessity, achieving high-performance while maintaining all of
Earley's power in parsing any CFG.
"""
# Author: Erez Shinan (2017)
# Email : erezshin@gmail.com

import collections
import itertools

from ..common import ParseError, is_terminal
from ..lexer import Token, UnexpectedInput
from ..tree import Tree
from .grammar_analysis import GrammarAnalyzer
from .earley import ApplyCallbacks
from .earley_common import Column, Item
from .earley_forest import ForestToTreeVisitor, ForestSumVisitor, SymbolNode, TokenNode, PackedNode

class Parser:
    def __init__(self,  parser_conf, term_matcher, resolve_ambiguity=True, forest_sum_visitor = ForestSumVisitor, ignore=()):
        analysis = GrammarAnalyzer(parser_conf)
        self.parser_conf = parser_conf
        self.ignore = list(ignore)

        self.FIRST = analysis.FIRST
        self.NULLABLE = analysis.NULLABLE
        self.postprocess = {}
        self.predictions = {}

        self.resolve_ambiguity = resolve_ambiguity
        self.forest_sum_visitor = forest_sum_visitor

        for rule in parser_conf.rules:
            self.postprocess[rule] = getattr(parser_conf.callback, rule.alias)
            self.predictions[rule.origin] = [x.rule for x in analysis.expand_rule(rule.origin)]

        self.term_matcher = term_matcher

    def parse(self, stream, start_symbol=None):
        start_symbol = start_symbol or self.parser_conf.start
        delayed_matches = collections.defaultdict(list)
        match = self.term_matcher

        # Held Completions (H in E.Scotts paper).
        held_completions = {}

        # Cache for nodes & tokens created in a particular parse step.
        node_cache = {}
        token_cache = {}

        text_line = 1
        text_column = 0

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

        def scan(i, column, to_scan):
            """The core Earley Scanner.

            This is a custom implementation of the scanner that uses the
            Lark lexer to match tokens. The scan list is built by the
            Earley predictor, based on the previously completed tokens.
            This ensures that at each phase of the parse we have a custom
            lexer context, allowing for more complex ambiguities."""

            # 1) Collate all terminals that request the same regular expression.
            # This reduces pressure on regular expression performance when
            # many non-terminals can request the same token in a pass.
            sort = sorted(to_scan, key=lambda item: item.expect)
            expectations = {key: set(values) for key, values in itertools.groupby(sort, lambda item: item.expect)}

            # 2) Loop the expectations and ask the lexer to match.
            # Since regexp is forward looking on the input stream, and we only
            # want to process tokens when we hit the point in the stream at which
            # they complete, we push all tokens into a buffer (delayed_matches), to
            # be held possibly for a later parse step when we reach the point in the
            # input stream at which they complete.
            for expect in expectations:
                m = match(expect, stream, i)
                if m:

                    t = Token(expect, m.group(0), i, text_line, text_column)
                    delayed_matches[m.end()].extend( [ (item, column, t) for item in expectations[expect] ] )

                    s = m.group(0)
                    for j in range(1, len(s)):
                        m = match(expect, s[:-j])
                        if m:
                            t = Token(expect, m.group(0), i, text_line, text_column)
                            delayed_matches[i+m.end()].extend( [ (item, column, t) for item in expectations[expect] ] )

                    # Remove any items that successfully matched in this pass from the to_scan buffer.
                    # This ensures we don't carry over tokens that already matched, if we're ignoring below.
                    to_scan -= expectations[expect]

            # 3) Process any ignores. This is typically used for e.g. whitespace.
            # We carry over any unmatched items from the to_scan buffer to be matched again after
            # the ignore. This should allow us to use ignored symbols in non-terminals to implement
            # e.g. mandatory spacing.
            for x in self.ignore:
                m = match(x, stream, i)
                if m:
                    # Carry over any items still in the scan buffer, to past the end of the ignored items.
                    delayed_matches[m.end()].extend([(item, column, None) for item in to_scan ])

                    # If we're ignoring up to the end of the file, # carry over the start symbol if it already completed.
                    delayed_matches[m.end()].extend([(item, column, None) for item in column.items if item.is_complete and item.s == start_symbol])

            next_set = Column(i + 1, self.FIRST)    # Ei+1
            next_to_scan = set()

            ## 4) Process Tokens from delayed_matches.
            # This is the core of the Earley scanner. Create an SPPF node for each Token,
            # and create the symbol node in the SPPF tree. Advance the item that completed,
            # and add the resulting new item to either the Earley set (for processing by the
            # completer/predictor) or the to_scan buffer for the next parse step.
            for item, start, token in delayed_matches[i+1]:
                if token is not None:
                    new_item = item.advance()
                    new_item.node = make_symbol_node(new_item.s, new_item.start, column)
                    token_node = make_token_node(token, start, next_set)
                    new_item.node.add_family(make_packed_node(new_item.s, item.rule, new_item.start, item.node, token_node))
                else:
                    new_item = item

                if new_item.is_terminal:
                    # add (B ::= Aai+1.B, h, y) to Q'
                    next_to_scan.add(new_item)
                else:
                    # add (B ::= Aa+1.B, h, y) to Ei+1
                    next_set.add(new_item)

            del delayed_matches[i+1]    # No longer needed, so unburden memory

            if not next_set and not delayed_matches and not next_to_scan:
                raise UnexpectedInput(stream, i, text_line, text_column, {item for item in to_scan})

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
            column, to_scan = scan(i, column, to_scan)

            if token == '\n':
                text_line += 1
                text_column = 0
            else:
                text_column += 1

        predict_and_complete(column, to_scan)

        ## Column is now the final column in the parse. If the parse was successful, the start
        # symbol should have been completed in the last step of the Earley cycle, and will be in
        # this column. Find the item for the start_symbol, which is the root of the SPPF tree.
        solutions = [n.node for n in column.items if n.is_complete and n.node is not None and n.s == start_symbol and n.start is column0]

        if not solutions:
            expected_tokens = [t.expect for t in to_scan]
            raise ParseError('Unexpected end of input! Expecting a terminal of: %s' % expected_tokens)
        elif len(solutions) > 1:
            raise Exception('Earley should not generate more than one start symbol - bug')

        ## If we're not resolving ambiguity, we just return the root of the SPPF tree to the caller.
        # This means the caller can work directly with the SPPF tree.
        if not self.resolve_ambiguity:
            return solutions[0]

        # ... otherwise, disambiguate and convert the SPPF to an AST, removing any ambiguities
        # according to the rules.
        tree = ForestToTreeVisitor(solutions[0], self.forest_sum_visitor).go()
        return ApplyCallbacks(self.postprocess).transform(tree)
