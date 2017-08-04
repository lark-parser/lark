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

from collections import defaultdict

from ..common import ParseError, UnexpectedToken, Terminal
from ..lexer import Token
from ..tree import Tree
from .grammar_analysis import GrammarAnalyzer

from .earley import ResolveAmbig, ApplyCallbacks, Item, NewsList, Derivation, END_TOKEN, Column

class Parser:
    def __init__(self, rules, start_symbol, callback, resolve_ambiguity=True, ignore=()):
        self.analysis = GrammarAnalyzer(rules, start_symbol)
        self.start_symbol = start_symbol
        self.resolve_ambiguity = resolve_ambiguity
        self.ignore = list(ignore)


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
        delayed_matches = defaultdict(list)

        text_line = 1
        text_column = 0

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
            for x in self.ignore:
                m = x.match(stream, i)
                if m:
                    return column

            to_scan = column.to_scan.get_news()

            for item in to_scan:
                m = item.expect.match(stream, i)
                if m:
                    t = Token(item.expect.name, m.group(0), i, text_line, text_column)
                    delayed_matches[m.end()].append(item.advance(t))

                    s = m.group(0)
                    for j in range(1, len(s)):
                        m = item.expect.match(s[:-j])
                        if m:
                            delayed_matches[m.end()].append(item.advance(m.group(0)))

            next_set = Column(i+1)
            next_set.add(delayed_matches[i+1])
            del delayed_matches[i+1]    # No longer needed, so unburden memory

            return next_set

        # Main loop starts
        column0 = Column(0)
        column0.add(predict(start_symbol, column0))

        column = column0
        for i, token in enumerate(stream):
            predict_and_complete(column)
            column = scan(i, token, column)

            if token == '\n':
                text_line += 1
                text_column = 0
            else:
                text_column += 1


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


