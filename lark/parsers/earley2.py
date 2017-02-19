from ..utils import classify, classify_bool, bfs, fzset
from ..common import GrammarError, is_terminal
from lalr_analysis import Rule, RulePtr, GrammarAnalyzer

class Item:
    def __init__(self, rule_ptr, start):
        self.rule_ptr = rule_ptr
        self.start = start

    @property
    def expect(self):
        return self.rule_ptr.next

    @property
    def is_complete(self):
        return self.rule_ptr.is_satisfied

    def advance(self):
        return Item(self.rule_ptr.advance(self.expect), self.start)

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
            return {Item(rp, i) for rp in self.analyzer.expand_rule(symbol)}

        def scan(item, inp):
            if item.expect == inp:   # TODO Do a smarter match, i.e. regexp
                return {item.advance()}
            else:
                return set()

        def complete(item, table):
            print "Complete:", item
            name = item.rule_ptr.rule.origin
            return {old_item.advance() for old_item in table[item.start]
                                       if old_item.expect == name}

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

        # Main loop starts

        table = [predict(self.start, 0)]

        for i, char in enumerate(stream):
            process_column(i, char)

        process_column(len(stream), None)





# rules = [
#     ('a', ['a', 'A']),
#     ('a', ['A']),
# ]

# p = Parser(rules, 'a')
# p.parse('AAA')

rules = [
    ('sum', ['sum', "A", 'product']),
    ('sum', ['product']),
    ('product', ['product', "M", 'factor']),
    ('product', ['factor']),
    ('factor', ['L', 'sum', 'R']),
    ('factor', ['number']),
    ('number', ['N', 'number']),
    ('number', ['N']),
]

p = Parser(rules, 'sum')
p.parse('NALNMNANR')
