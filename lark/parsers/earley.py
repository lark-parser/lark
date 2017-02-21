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

    def __repr__(self):
        before = map(str, self.rule.expansion[:self.ptr])
        after = map(str, self.rule.expansion[self.ptr:])
        return '<(%d) %s : %s * %s>' % (self.start, self.rule.origin, ' '.join(before), ' '.join(after))


class NewsList(list):
    def __init__(self, initial=None):
        list.__init__(self, initial or [])
        self.last_iter = 0

    def get_news(self):
        i = self.last_iter
        self.last_iter = len(self)
        return self[i:]


class Column:
    def __init__(self):
        self.to_reduce = NewsList()
        self.to_predict = NewsList()
        self.to_scan = NewsList()
        self.item_count = 0

    def add(self, items):
        self.item_count += len(items)
        for item in items:
            if item.is_complete:
                if item not in self.to_reduce:  # Avoid infinite loop
                    self.to_reduce.append(item)
            else:
                if is_terminal(item.expect):
                    self.to_scan.append(item)
                else:
                    self.to_predict.append(item)

    def __nonzero__(self):
        return bool(self.item_count)

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
                self.predictions[rule.origin] = [x.rule for x in self.analysis.expand_rule(rule.origin)]

    def parse(self, stream):
        # Define parser functions

        def predict(nonterm, i):
            assert not is_terminal(nonterm), nonterm
            return [Item(rule, 0, i, []) for rule in self.predictions[nonterm]]

        def complete(item, table):
            name = item.rule.origin
            item.data = self.postprocess[item.rule](item.data)
            return [i.advance(item.data) for i in table[item.start].to_predict
                    if i.expect == name]

        def process_column(i, token):
            assert i == len(table)-1
            cur_set = table[i]
            next_set = Column()

            while True:
                to_predict = {x.expect for x in cur_set.to_predict.get_news()
                              if x.ptr}  # if not part of an already predicted batch
                to_reduce = cur_set.to_reduce.get_news()
                if not (to_predict or to_reduce):
                    break

                for nonterm in to_predict:
                    cur_set.add( predict(nonterm, i) )
                for item in to_reduce:
                    cur_set.add( complete(item, table) )


            for item in cur_set.to_scan.get_news():
                match = item.expect[0](token) if callable(item.expect[0]) else item.expect[0] == token.type
                if match:
                    next_set.add([item.advance(stream[i])])

            if not next_set and token.type != '$end':
                expect = [i.expect for i in cur_set.to_scan]
                raise UnexpectedToken(token, expect, stream, i)

            table.append(next_set)

        # Main loop starts
        table = [Column()]
        table[0].add(predict(self.start, 0))

        for i, char in enumerate(stream):
            process_column(i, char)

        process_column(len(stream), EndToken())

        # Parse ended. Now build a parse tree
        solutions = [n.data for n in table[len(stream)].to_reduce
                     if n.rule.origin==self.start and n.start==0]

        if not solutions:
            raise ParseError('Incomplete parse: Could not find a solution to input')

        return solutions
