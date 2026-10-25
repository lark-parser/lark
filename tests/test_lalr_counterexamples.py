from unittest import TestCase
from unittest.mock import patch

from lark import Lark, Tree
from lark.common import ParserConf
from lark.exceptions import GrammarError
from lark.grammar import NonTerminal
from lark.parsers.lalr_analysis import LALR_Analyzer
from lark.parsers.lalr_counterexamples import CounterexampleGenerator, _DOT


class TestLalrCounterexamples(TestCase):
    dangling_else = '''
        start: stmt
        stmt: "if" expr "then" stmt "else" stmt | "if" expr "then" stmt | "s"
        expr: "e"
        %ignore " "
    '''

    @staticmethod
    def analyze(grammar, start=('start',)):
        parser = Lark(grammar, parser='earley', start=list(start))
        analyzer = LALR_Analyzer(ParserConf(parser.rules, {}, list(start)))
        analyzer.compute_lr0_states()
        analyzer.compute_reads_relations()
        analyzer.compute_includes_lookback()
        analyzer.compute_lookaheads()
        return analyzer

    @staticmethod
    def conflicts(analyzer):
        for state in analyzer.lr0_itemsets:
            for lookahead, rules in state.lookaheads.items():
                rules = sorted(rules, key=CounterexampleGenerator._rule_key)
                if len(rules) > 1:
                    yield state, lookahead, rules[0], rules[1]
                elif lookahead in state.transitions:
                    yield state, lookahead, rules[0], None

    @staticmethod
    def symbols(tree):
        return list(tree.scan_values(lambda value: not isinstance(value, Tree)))

    def assert_derivations(self, analyzer, state, lookahead, trees):
        self.assertIsNotNone(trees)
        for tree in trees:
            leaves = self.symbols(tree)
            self.assertEqual(sum(s is _DOT for s in leaves), 1)
            position = leaves.index(_DOT)
            if lookahead.name == '$END':
                self.assertEqual(position, len(leaves) - 1)
            else:
                self.assertEqual(leaves[position + 1], lookahead)
            reached = analyzer.lr0_start_states[tree.data]
            for symbol in leaves[:position]:
                reached = reached.transitions[symbol]
            self.assertIs(reached, state)
            for node in tree.iter_subtrees():
                expansion = tuple(
                    NonTerminal(child.data) if isinstance(child, Tree) else child
                    for child in node.children if child is not _DOT
                )
                rules = analyzer.lr0_rules_by_origin[NonTerminal(node.data)]
                self.assertIn(expansion, [tuple(rule.expansion) for rule in rules])

    def assert_examples(self, grammar, expected, start=('start',)):
        analyzer = self.analyze(grammar, start)
        generator = CounterexampleGenerator(analyzer)
        conflicts = list(self.conflicts(analyzer))
        self.assertTrue(conflicts)
        examples = []
        for state, lookahead, rule, other_rule in conflicts:
            trees = generator.generate(state, lookahead, rule, other_rule)
            self.assert_derivations(analyzer, state, lookahead, trees)
            examples.append(tuple(
                tuple('*' if symbol is _DOT else symbol.name for symbol in self.symbols(tree))
                for tree in trees
            ))
        self.assertIn(expected, examples)

    def test_strict_shift_reduce_example_respects_lookahead(self):
        with self.assertRaises(GrammarError) as error:
            Lark(self.dangling_else, parser='lalr', strict=True)
        message = str(error.exception)
        self.assertIn('Example: IF expr THEN IF expr THEN stmt * ELSE stmt', message)
        self.assertIn('Reduce derivation:', message)
        self.assertIn('Shift derivation:', message)
        self.assertNotIn('Example: IF expr THEN stmt * ELSE stmt', message)

        parser = Lark(self.dangling_else, parser='earley', ambiguity='explicit')
        tree = parser.parse('if e then if e then s else s')
        self.assertTrue(any(t.data == '_ambig' and len(t.children) == 2
                            for t in tree.iter_subtrees()))

    def test_debug_shift_reduce_example(self):
        with self.assertLogs('lark', level='WARNING') as logs:
            Lark(self.dangling_else, parser='lalr', debug=True)
        self.assertIn('Example: IF expr THEN IF expr THEN stmt * ELSE stmt', '\n'.join(logs.output))

    def test_operator_derivations(self):
        example = ('expr', 'PLUS', 'expr', '*', 'PLUS', 'expr')
        self.assert_examples('''start: expr
            expr: expr "+" expr | "n"
        ''', (example, example))

    def test_reduce_reduce_derivations(self):
        grammar = '''start: a | b
            a: "x"
            b: "x"
        '''
        example = ('X', '*')
        self.assert_examples(grammar, (example, example))
        with self.assertRaises(GrammarError) as error:
            Lark(grammar, parser='lalr')
        self.assertIn('Example: X *', str(error.exception))

    def test_nullable_context(self):
        example = ('IF', 'cond', 'THEN', 'IF', 'cond', 'THEN', 'outer', '*', 'ELSE', 'outer')
        self.assert_examples('''start: outer
            outer: "if" cond "then" outer tail | "s"
            tail: "else" outer |
            cond: "x"
        ''', (example, example))

    def test_lookahead_after_nullable_symbol(self):
        example = ('P', 'A', '*', 'X')
        self.assert_examples('''start: "p" chosen pad "x" | "p" "a" "x"
            chosen: "a"
            pad:
        ''', (example, example))

    def test_nullable_cycle(self):
        example = ('P', 'A', '*', 'X')
        self.assert_examples('''start: "p" chosen pad "x" | "p" "a" "x"
            chosen: "a"
            pad: loop |
            loop: pad
        ''', (example, example))

    def test_lr1_contexts_are_not_reported_as_ambiguity(self):
        self.assert_examples('''start: "a" x "d" | "b" x "e" | "a" y "e" | "b" y "d"
            x: "c"
            y: "c"
        ''', (('A', 'C', '*', 'D'), ('B', 'C', '*', 'D')))

    def test_multiple_start_symbols(self):
        self.assert_examples('''first: "a" x "d" | "a" y "e"
            second: "b" x "e" | "b" y "d"
            x: "c"
            y: "c"
        ''', (('A', 'C', '*', 'D'), ('B', 'C', '*', 'D')), start=('first', 'second'))

    def test_identical_yields_from_different_start_symbols(self):
        analyzer = self.analyze('''first: x "d" | y "e"
            second: x "e" | y "d"
            x: "c"
            y: "c"
        ''', start=('first', 'second'))
        generator = CounterexampleGenerator(analyzer)
        for state, lookahead, rule, other_rule in self.conflicts(analyzer):
            trees = generator.generate(state, lookahead, rule, other_rule)
            self.assert_derivations(analyzer, state, lookahead, trees)
            self.assertNotEqual(trees[0].data, trees[1].data)
            message = generator.explain(state, lookahead, rule, other_rule)
            self.assertNotIn('Example:', message)
            self.assertEqual(message.count('Reduce example:'), 2)

    def test_reduce_reduce_priority(self):
        with self.assertRaises(GrammarError) as error:
            Lark('''start: a | b | c
                a.1: "x"
                b.2: "x"
                c.2: "x"
            ''', parser='lalr')
        message = str(error.exception)
        self.assertIn('start\n  b\n', message)
        self.assertIn('start\n  c\n', message)
        self.assertNotIn('start\n  a\n', message)

    def test_unproductive_grammar_has_no_witness(self):
        analyzer = self.analyze('''start: a | b
            a: "x" dead
            b: "x" dead
            dead: "z" dead
        ''')
        generator = CounterexampleGenerator(analyzer)
        conflicts = list(self.conflicts(analyzer))
        self.assertTrue(conflicts)
        for state, lookahead, rule, other_rule in conflicts:
            self.assertIsNone(generator.generate(state, lookahead, rule, other_rule))

    def test_budget_preserves_original_diagnostic(self):
        def limited(analyzer):
            return CounterexampleGenerator(analyzer, max_nodes=1)

        with patch('lark.parsers.lalr_analysis.CounterexampleGenerator', limited):
            with self.assertRaises(GrammarError) as error:
                Lark(self.dangling_else, parser='lalr', strict=True)
        self.assertIn('Shift/Reduce conflict', str(error.exception))
        self.assertNotIn('Example:', str(error.exception))

    def test_large_nullable_derivation_preserves_original_diagnostic(self):
        for suffix in ('pad "x"', '"x" pad'):
            with self.subTest(suffix=suffix):
                rules = [f'start: "p" chosen {suffix} | "p" "a" "x"',
                         'chosen: "a"', 'pad: n0']
                rules.extend(f'n{i}: n{i + 1} n{i + 1}' for i in range(13))
                rules.append('n13:')
                with self.assertRaises(GrammarError) as error:
                    Lark('\n'.join(rules), parser='lalr', strict=True)
                message = str(error.exception)
                self.assertIn('Shift/Reduce conflict', message)
                self.assertLess(len(message), 1024)
                self.assertFalse('Example:' in message)

    def test_no_search_for_conflict_free_grammar(self):
        with patch('lark.parsers.lalr_analysis.CounterexampleGenerator') as generator:
            Lark('start: "a"', parser='lalr', debug=True, strict=True).parse('a')
        generator.assert_not_called()
