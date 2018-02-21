"This module implements an experimental Earley Parser with a dynamic lexer"

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
# Instead of running a lexer beforehand, or using a costy char-by-char method, this parser
# uses regular expressions by necessity, achieving high-performance while maintaining all of
# Earley's power in parsing any CFG.
#
#
# Author: Erez Shinan (2017)
# Email : erezshin@gmail.com

import collections

from ..common import ParseError, is_terminal
from ..lexer import Token, UnexpectedInput
from ..tree import Tree
from .grammar_analysis import GrammarAnalyzer
from .earley import ApplyCallbacks
from .earley_common import Column, Item, LR0
from .earley_forest import Forest, ForestToTreeVisitor

class Parser:
    def __init__(self,  parser_conf, term_matcher, resolve_ambiguity=None, ignore=()):
        self.analysis = GrammarAnalyzer(parser_conf)
        self.parser_conf = parser_conf
        self.resolve_ambiguity = resolve_ambiguity
        self.ignore = list(ignore)

        self.FIRST = self.analysis.FIRST
        self.NULLABLE = self.analysis.NULLABLE
        self.postprocess = {}
        self.predictions = {}
        for rule in parser_conf.rules:
            self.postprocess[rule] = getattr(parser_conf.callback, rule.alias)
            self.predictions[rule.origin] = [x.rule for x in self.analysis.expand_rule(rule.origin)]

        self.term_matcher = term_matcher

    def parse(self, stream, start_symbol=None):
        # Define parser functions
        start_symbol = start_symbol or self.parser_conf.start
        delayed_matches = collections.defaultdict(list)
        match = self.term_matcher
        forest = Forest()
        held_completions = collections.defaultdict(list)

        text_line = 1
        text_column = 0

        def add(column, items, to_scan, item):
            if item not in column.items:
                column.add(item)
                items.append(item)
            if is_terminal(item.s.expect):
                to_scan.add(item)

        def predict(item, column, items, to_scan):
            for rule in self.predictions[item.s.expect]:
                lr0 = LR0(rule, 0)
                new_item = Item(lr0, column, None)
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
            items = list(column.items) # R
            while items:
                item = items.pop(0)
                if item.is_complete:
                    complete(item, column, items, to_scan)
                elif not is_terminal(item.s.expect):
                    predict(item, column, items, to_scan)

        def scan(i, column, to_scan):
            for item in set(to_scan):
                m = match(item.s.expect, stream, i)
                if m:
                    t = Token(item.s.expect, m.group(0), i, text_line, text_column)
                    delayed_matches[m.end()].append((item, column, t))

                    s = m.group(0)
                    for j in range(1, len(s)):
                        m = match(item.s.expect, s[:-j])
                        if m:
                            t = Token(item.s.expect, m.group(0), i, text_line, text_column)
                            delayed_matches[i+m.end()].append((item, column, t))
                    to_scan.remove(item)

            for x in self.ignore:
                m = match(x, stream, i)
                if m:
                    # Carry over any items currently in the scan buffer, to past # the end of the ignored items.
                    delayed_matches[m.end()].extend([(item, column, None) for item in to_scan])

                    # If we're ignoring up to the end of the file, # carry over the start symbol if it already completed.
                    delayed_matches[m.end()].extend([(item, column, None) for item in column.items if item.is_complete and item.s.rule.origin == start_symbol])

            next_set = Column(i + 1, self.FIRST)    # Ei+1
            next_to_scan = set()                                                   # Q'
            for item, start, token in delayed_matches[i+1]:
                if token is not None:
                    token_node = forest.make_token_node(token, start, next_set)
                    new_item = item.advance()
                    new_item.node = forest.make_intermediate_or_symbol_node(new_item.s, new_item.start, next_set)
                    new_item.node.add_family(new_item.s, new_item.start, item.node, token_node)
                else:
                    new_item = item

                if new_item not in next_set.items:
                    next_set.add(new_item)
                if is_terminal(new_item.s.expect):
                    next_to_scan.add(new_item)

            del delayed_matches[i+1]    # No longer needed, so unburden memory

            if not next_set and not delayed_matches and not next_to_scan:
                raise UnexpectedInput(stream, i, text_line, text_column, {item.s.expect for item in to_scan})

            return next_set, next_to_scan

        # Main loop starts
        column0 = Column(0, self.FIRST)
        column = column0
        to_scan = set()

	### Predict for the start_symbol
        for rule in self.predictions[start_symbol]:
            lr0 = LR0(rule, 0)
            item = Item(lr0, column0, None)
            column.add(item)
            if is_terminal(item.s.expect):
                to_scan.add(item)

        for i, token in enumerate(stream):
            predict_and_complete(column, to_scan)
            column, to_scan = scan(i, column, to_scan)

            if token == '\n':
                text_line += 1
                text_column = 0
            else:
                text_column += 1

        predict_and_complete(column, to_scan)

        solutions = [n.node for n in column.items if n.is_complete and n.node is not None and n.s.rule.origin == start_symbol and n.start is column0]

        if not solutions:
            expected_tokens = [t.s.expect for t in to_scan]
            raise ParseError('Unexpected end of input! Expecting a terminal of: %s' % expected_tokens)
        elif len(solutions) > 1:
            raise Exception('Earley should not generate more than one start symbol - bug')

        forest_visitor = ForestToTreeVisitor(forest, solutions[0])
        tree = forest_visitor.go()

        if self.resolve_ambiguity:
            tree = self.resolve_ambiguity(tree)

        return ApplyCallbacks(self.postprocess).transform(tree)
