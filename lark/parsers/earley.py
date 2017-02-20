from ..common import ParseError, UnexpectedToken, is_terminal
from .grammar_analysis import GrammarAnalyzer

class EndToken(str):
    type = '$end'

class Item:
    def __init__(self, rule, ptr, start, data):
        self.rule = rule
        self.ptr = ptr
        self.start = start
        self.data = data

    @property
    def expect(self):
        return self.rule.expansion[self.ptr]

    @property
    def is_complete(self):
        return self.ptr == len(self.rule.expansion)

    def advance(self, data):
        return Item(self.rule, self.ptr+1, self.start, self.data + [data])

    def __eq__(self, other):
        return self.start == other.start and self.ptr == other.ptr and self.rule == other.rule
    def __hash__(self):
        return hash((self.rule, self.ptr, self.start))


class Parser:
    def __init__(self, parser_conf):
        self.analysis = GrammarAnalyzer(parser_conf.rules, parser_conf.start)
        self.start = parser_conf.start

        self.postprocess = {}
        self.predictions = {}
        for rule in self.analysis.rules:
            if rule.origin != '$root':  # XXX kinda ugly
                a = rule.alias
                self.postprocess[rule] = a if callable(a) else getattr(parser_conf.callback, a)
                self.predictions[rule.origin] = [(x.rule, x.index) for x in self.analysis.expand_rule(rule.origin)]

    def parse(self, stream):
        # Define parser functions

        def predict(symbol, i):
            assert not is_terminal(symbol), symbol
            return {Item(rule, index, i, []) for rule, index in self.predictions[symbol]}

        def complete(item, table):
            item.data = self.postprocess[item.rule](item.data)
            return {old_item.advance(item.data) for old_item in table[item.start]
                    if not old_item.is_complete and old_item.expect == item.rule.origin}

        def process_column(i, token):
            assert i == len(table)-1
            cur_set = table[i]
            next_set = set()

            to_process = cur_set
            while to_process:
                new_items = set()
                for item in to_process:
                    if item.is_complete:
                        new_items |= complete(item, table)
                    else:
                        if is_terminal(item.expect):
                            # scan
                            match = item.expect[0](token) if callable(item.expect[0]) else item.expect[0] == token.type
                            if match:
                                next_set.add(item.advance(stream[i]))
                        else:
                            if item.ptr: # part of an already predicted batch
                                new_items |= predict(item.expect, i)

                to_process = new_items - cur_set    # TODO: is this precaution necessary?
                cur_set |= to_process


            if not next_set and token.type != '$end':
                expect = filter(is_terminal, [x.expect for x in cur_set if not x.is_complete])
                raise UnexpectedToken(token, expect, stream, i)

            table.append(next_set)

        # Main loop starts
        table = [predict(self.start, 0)]

        for i, char in enumerate(stream):
            process_column(i, char)

        process_column(len(stream), EndToken())

        # Parse ended. Now build a parse tree
        solutions = [n.data for n in table[len(stream)]
                     if n.is_complete and n.rule.origin==self.start and n.start==0]

        if not solutions:
            raise ParseError('Incomplete parse: Could not find a solution to input')

        return solutions
