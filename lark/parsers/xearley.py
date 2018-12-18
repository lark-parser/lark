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

from collections import defaultdict, deque

from ..exceptions import ParseError, UnexpectedCharacters
from ..lexer import Token
from .grammar_analysis import GrammarAnalyzer
from ..grammar import NonTerminal, Terminal
from .earley import ApplyCallbacks
from .earley_common import Item, TransitiveItem
from .earley_forest import ForestToTreeVisitor, ForestSumVisitor, SymbolNode, Forest


class Parser:
    def __init__(self,  parser_conf, term_matcher, resolve_ambiguity=True, forest_sum_visitor = ForestSumVisitor, ignore = (), complete_lex = False):
        analysis = GrammarAnalyzer(parser_conf)
        self.parser_conf = parser_conf
        self.resolve_ambiguity = resolve_ambiguity
        self.ignore = [Terminal(t) for t in ignore]
        self.complete_lex = complete_lex

        self.FIRST = analysis.FIRST
        self.NULLABLE = analysis.NULLABLE
        self.callbacks = {}
        self.predictions = {}

        ## These could be moved to the grammar analyzer. Pre-computing these is *much* faster than
        #  the slow 'isupper' in is_terminal.
        self.TERMINALS = { sym for r in parser_conf.rules for sym in r.expansion if sym.is_term }
        self.NON_TERMINALS = { sym for r in parser_conf.rules for sym in r.expansion if not sym.is_term }

        for rule in parser_conf.rules:
            self.callbacks[rule] = getattr(parser_conf.callback, rule.alias or rule.origin, None)
            self.predictions[rule.origin] = [x.rule for x in analysis.expand_rule(rule.origin)]

        self.forest_tree_visitor = ForestToTreeVisitor(forest_sum_visitor, self.callbacks)
        self.term_matcher = term_matcher

    def parse(self, stream, start_symbol=None):
        start_symbol = NonTerminal(start_symbol or self.parser_conf.start)
        delayed_matches = defaultdict(list)
        match = self.term_matcher

        # Held Completions (H in E.Scotts paper).
        held_completions = {}

        # Cache for nodes & tokens created in a particular parse step.
        node_cache = {}
        token_cache = {}
        columns = []
        transitives = []

        text_line = 1
        text_column = 1

        def is_quasi_complete(item):
            if item.is_complete:
                return True

            quasi = item.advance()
            while not quasi.is_complete:
                symbol = quasi.expect
                if symbol not in self.NULLABLE:
                    return False
                if quasi.rule.origin == start_symbol and symbol == start_symbol:
                    return False
                quasi = quasi.advance()
            return True

        def create_leo_transitives(item, trule, previous, visited = None):
            if visited is None:
                visited = set()

            if item.rule.origin in transitives[item.start]:
                previous = trule = transitives[item.start][item.rule.origin]
                return trule, previous

            is_empty_rule = not self.FIRST[item.rule.origin]
            if is_empty_rule:
                return trule, previous

            originator = None
            for key in columns[item.start]:
                if key.expect is not None and key.expect == item.rule.origin:
                    if originator is not None:
                        return trule, previous
                    originator = key

            if originator is None:
                return trule, previous

            if originator in visited:
                return trule, previous

            visited.add(originator)
            if not is_quasi_complete(originator):
                return trule, previous

            trule = originator.advance()
            if originator.start != item.start:
                visited.clear()

            trule, previous = create_leo_transitives(originator, trule, previous, visited)
            if trule is None:
                return trule, previous

            titem = None
            if previous is not None:
                titem = TransitiveItem(item.rule.origin, trule, originator, previous.column)
                previous.next_titem = titem
            else:
                titem = TransitiveItem(item.rule.origin, trule, originator, item.start)

            previous = transitives[item.start][item.rule.origin] = titem
            return trule, previous

        def predict_and_complete(i, to_scan):
            """The core Earley Predictor and Completer.

            At each stage of the input, we handling any completed items (things
            that matched on the last cycle) and use those to predict what should
            come next in the input stream. The completions and any predicted
            non-terminals are recursively processed until we reach a set of,
            which can be added to the scan list for the next scanner cycle."""
            held_completions.clear()

            column = columns[i]
            # R (items) = Ei (column.items)
            items = deque(column)
            while items:
                item = items.pop()    # remove an element, A say, from R

                ### The Earley completer
                if item.is_complete:   ### (item.s == string)
                    if item.node is None:
                        label = (item.s, item.start, i)
                        item.node = node_cache[label] if label in node_cache else node_cache.setdefault(label, SymbolNode(*label))
                        item.node.add_family(item.s, item.rule, item.start, None, None)

                    create_leo_transitives(item, None, None)

                    ###R Joop Leo right recursion Completer
                    if item.rule.origin in transitives[item.start]:
                        transitive = transitives[item.start][item.s]
                        if transitive.previous in transitives[transitive.column]:
                            root_transitive = transitives[transitive.column][transitive.previous]
                        else:
                            root_transitive = transitive

                        label = (root_transitive.s, root_transitive.start, i)
                        node = vn = node_cache[label] if label in node_cache else node_cache.setdefault(label, SymbolNode(*label))
                        vn.add_path(root_transitive, item.node)

                        new_item = Item(transitive.rule, transitive.ptr, transitive.start)
                        new_item.node = vn
                        if new_item.expect in self.TERMINALS:
                            # Add (B :: aC.B, h, y) to Q
                            to_scan.add(new_item)
                        elif new_item not in column:
                            # Add (B :: aC.B, h, y) to Ei and R
                            column.add(new_item)
                            items.append(new_item)
                    ###R Regular Earley completer
                    else:
                        # Empty has 0 length. If we complete an empty symbol in a particular
                        # parse step, we need to be able to use that same empty symbol to complete
                        # any predictions that result, that themselves require empty. Avoids
                        # infinite recursion on empty symbols.
                        # held_completions is 'H' in E.Scott's paper.
                        is_empty_item = item.start == i
                        if is_empty_item:
                            held_completions[item.rule.origin] = item.node

                        originators = [originator for originator in columns[item.start] if originator.expect is not None and originator.expect == item.s]
                        for originator in originators:
                            new_item = originator.advance()
                            label = (new_item.s, originator.start, i)
                            new_item.node = node_cache[label] if label in node_cache else node_cache.setdefault(label, SymbolNode(*label))
                            new_item.node.add_family(new_item.s, new_item.rule, i, originator.node, item.node)
                            if new_item.expect in self.TERMINALS:
                                # Add (B :: aC.B, h, y) to Q
                                to_scan.add(new_item)
                            elif new_item not in column:
                                # Add (B :: aC.B, h, y) to Ei and R
                                column.add(new_item)
                                items.append(new_item)

                ### The Earley predictor
                elif item.expect in self.NON_TERMINALS: ### (item.s == lr0)
                    new_items = []
                    for rule in self.predictions[item.expect]:
                        new_item = Item(rule, 0, i)
                        new_items.append(new_item)

                    # Process any held completions (H).
                    if item.expect in held_completions:
                        new_item = item.advance()
                        label = (new_item.s, item.start, i)
                        new_item.node = node_cache[label] if label in node_cache else node_cache.setdefault(label, SymbolNode(*label))
                        new_item.node.add_family(new_item.s, new_item.rule, new_item.start, item.node, held_completions[item.expect])
                        new_items.append(new_item)

                    for new_item in new_items:
                        if new_item.expect in self.TERMINALS:
                            to_scan.add(new_item)
                        elif new_item not in column:
                            column.add(new_item)
                            items.append(new_item)

        def scan(i, to_scan):
            """The core Earley Scanner.

            This is a custom implementation of the scanner that uses the
            Lark lexer to match tokens. The scan list is built by the
            Earley predictor, based on the previously completed tokens.
            This ensures that at each phase of the parse we have a custom
            lexer context, allowing for more complex ambiguities."""

            # 1) Loop the expectations and ask the lexer to match.
            # Since regexp is forward looking on the input stream, and we only
            # want to process tokens when we hit the point in the stream at which
            # they complete, we push all tokens into a buffer (delayed_matches), to
            # be held possibly for a later parse step when we reach the point in the
            # input stream at which they complete.
            for item in set(to_scan):
                m = match(item.expect, stream, i)
                if m:
                    t = Token(item.expect.name, m.group(0), i, text_line, text_column)
                    delayed_matches[m.end()].append( (item, i, t) )

                    if self.complete_lex:
                        s = m.group(0)
                        for j in range(1, len(s)):
                            m = match(item.expect, s[:-j])
                            if m:
                                t = Token(item.expect.name, m.group(0), i, text_line, text_column)
                                delayed_matches[i+m.end()].append( (item, i, t) )

                    # Remove any items that successfully matched in this pass from the to_scan buffer.
                    # This ensures we don't carry over tokens that already matched, if we're ignoring below.
                    to_scan.remove(item)

            # 3) Process any ignores. This is typically used for e.g. whitespace.
            # We carry over any unmatched items from the to_scan buffer to be matched again after
            # the ignore. This should allow us to use ignored symbols in non-terminals to implement
            # e.g. mandatory spacing.
            for x in self.ignore:
                m = match(x, stream, i)
                if m:
                    # Carry over any items still in the scan buffer, to past the end of the ignored items.
                    delayed_matches[m.end()].extend([(item, i, None) for item in to_scan ])

                    # If we're ignoring up to the end of the file, # carry over the start symbol if it already completed.
                    delayed_matches[m.end()].extend([(item, i, None) for item in columns[i] if item.is_complete and item.s == start_symbol])

            next_to_scan = set()
            next_set = set()
            columns.append(next_set)
            next_transitives = dict()
            transitives.append(next_transitives)

            ## 4) Process Tokens from delayed_matches.
            # This is the core of the Earley scanner. Create an SPPF node for each Token,
            # and create the symbol node in the SPPF tree. Advance the item that completed,
            # and add the resulting new item to either the Earley set (for processing by the
            # completer/predictor) or the to_scan buffer for the next parse step.
            for item, start, token in delayed_matches[i+1]:
                if token is not None:
                    new_item = item.advance()
                    label = (new_item.s, new_item.start, i)
                    new_item.node = node_cache[label] if label in node_cache else node_cache.setdefault(label, SymbolNode(*label))
                    new_item.node.add_family(new_item.s, item.rule, new_item.start, item.node, token)
                else:
                    new_item = item

                if new_item.expect in self.TERMINALS:
                    # add (B ::= Aai+1.B, h, y) to Q'
                    next_to_scan.add(new_item)
                else:
                    # add (B ::= Aa+1.B, h, y) to Ei+1
                    next_set.add(new_item)

            del delayed_matches[i+1]    # No longer needed, so unburden memory

            if not next_set and not delayed_matches and not next_to_scan:
                raise UnexpectedCharacters(stream, i, text_line, text_column, {item.expect for item in to_scan}, set(to_scan))

            return next_to_scan

        # Main loop starts
        columns.append(set())
        transitives.append(dict())

        ## The scan buffer. 'Q' in E.Scott's paper.
        to_scan = set()

        ## Predict for the start_symbol.
        # Add predicted items to the first Earley set (for the predictor) if they
        # result in a non-terminal, or the scanner if they result in a terminal.
        for rule in self.predictions[start_symbol]:
            item = Item(rule, 0, 0)
            if item.expect in self.TERMINALS:
                to_scan.add(item)
            else:
                columns[0].add(item)

        ## The main Earley loop.
        # Run the Prediction/Completion cycle for any Items in the current Earley set.
        # Completions will be added to the SPPF tree, and predictions will be recursively
        # processed down to terminals/empty nodes to be added to the scanner for the next
        # step.
        i = 0
        for token in stream:
            predict_and_complete(i, to_scan)

            # Clear the node_cache and token_cache, which are only relevant for each
            # step in the Earley pass.
            node_cache.clear()
            token_cache.clear()
            node_cache.clear()
            to_scan = scan(i, to_scan)

            if token == '\n':
                text_line += 1
                text_column = 1
            else:
                text_column += 1
            i += 1

        predict_and_complete(i, to_scan)

        ## Column is now the final column in the parse. If the parse was successful, the start
        # symbol should have been completed in the last step of the Earley cycle, and will be in
        # this column. Find the item for the start_symbol, which is the root of the SPPF tree.
        solutions = [n.node for n in columns[i] if n.is_complete and n.node is not None and n.s == start_symbol and n.start == 0]

        if not solutions:
            expected_tokens = [t.expect for t in to_scan]
            raise ParseError('Unexpected end of input! Expecting a terminal of: %s' % expected_tokens)
        elif len(solutions) > 1:
            raise Exception('Earley should not generate more than one start symbol - bug')

        ## If we're not resolving ambiguity, we just return the root of the SPPF tree to the caller.
        # This means the caller can work directly with the SPPF tree.
        if not self.resolve_ambiguity:
            return Forest(solutions[0], self.callbacks)

        # ... otherwise, disambiguate and convert the SPPF to an AST, removing any ambiguities
        # according to the rules.
        return self.forest_tree_visitor.go(solutions[0])
