from ..common import ParseError, UnexpectedToken, is_terminal
from lalr_analysis import GrammarAnalyzer

from ..tree import Tree

class Item:
    def __init__(self, rule_ptr, start, data):
        self.rule_ptr = rule_ptr
        self.start = start
        self.data = data

    @property
    def expect(self):
        return self.rule_ptr.next

    @property
    def is_complete(self):
        return self.rule_ptr.is_satisfied

    @property
    def name(self):
        return self.rule_ptr.rule.origin

    def advance(self, data):
        return Item(self.rule_ptr.advance(self.expect), self.start, self.data + [data])

    def __eq__(self, other):
        return self.rule_ptr == other.rule_ptr and self.start == other.start
    def __hash__(self):
        return hash((self.rule_ptr, self.start))

    def __repr__(self):
        return '%s (%s)' % (self.rule_ptr, self.start)


class Parser:
    def __init__(self, rules, start):
        self.analyzer = GrammarAnalyzer(rules, start)
        self.start = start


    def parse(self, stream):
        # Define parser functions

        def predict(symbol, i):
            assert not is_terminal(symbol), symbol
            return {Item(rp, i, []) for rp in self.analyzer.expand_rule(symbol)}

        def scan(item, inp):
            if item.expect == inp:   # TODO Do a smarter match, i.e. regexp
                return {item.advance(inp)}
            else:
                return set()

        def complete(item, table):
            name = item.name
            item.data = Tree(name, item.data)
            return {old_item.advance(item.data) for old_item in table[item.start]
                    if not old_item.is_complete and old_item.expect == name}

        def process_column(i, char):
            cur_set = table[-1]
            next_set = set()
            table.append(next_set)

            to_process = cur_set
            while to_process:
                new_items = set()
                for item in to_process:
                    if item.is_complete:
                        new_items |= complete(item, table)
                    else:
                        if is_terminal(item.expect):
                            next_set |= scan(item, char)
                        else:
                            new_items |= predict(item.expect, i)

                to_process = new_items - cur_set
                cur_set |= to_process

            if not next_set and char != '$end':
                expect = filter(is_terminal, [i.expect for i in cur_set if not i.is_complete])
                raise UnexpectedToken(char, expect, stream, i)

        # Main loop starts

        table = [predict(self.start, 0)]

        for i, char in enumerate(stream):
            process_column(i, char)

        process_column(len(stream), '$end')

        # Parse ended. Now build a parse tree
        solutions = [n.data for n in table[len(stream)]
                     if n.is_complete and n.name==self.start and n.start==0]

        if not solutions:
            raise ParseError('Incomplete parse: Could not find a solution to input')

        return solutions





# rules = [
#     ('a', ['a', 'A']),
#     ('a', ['a', 'A', 'a']),
#     ('a', ['a', 'A', 'A', 'a']),
#     ('a', ['A']),
# ]

# p = Parser(rules, 'a')
# for x in p.parse('AAAA'):
#     print '->'
#     print x.pretty()

# rules = [
#     ('sum', ['sum', "A", 'product']),
#     ('sum', ['product']),
#     ('product', ['product', "M", 'factor']),
#     ('product', ['factor']),
#     ('factor', ['L', 'sum', 'R']),
#     ('factor', ['number']),
#     ('number', ['N', 'number']),
#     ('number', ['N']),
# ]

# p = Parser(rules, 'sum')
# print p.parse('NALNMNANR')
