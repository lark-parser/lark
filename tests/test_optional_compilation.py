"""Regression coverage for optional productions (issues #190 and #506)."""

import runpy
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from lark import Lark, Token, Transformer, Tree, UnexpectedInput
from lark.exceptions import GrammarError


def optional_fields(brackets=True, count=64):
    names = ['T%d' % i for i in range(count)]
    production = ' '.join('[%s]' % name if brackets else name + '?' for name in names)
    definitions = '\n'.join('%s: "<%d>"' % (name, i) for i, name in enumerate(names))
    return production, definitions


def expected_fields(indices, brackets=True, count=64):
    present = set(indices)
    return [
        Token('T%d' % i, '<%d>' % i) if i in present else None
        for i in range(count)
        if brackets or i in present
    ]


def token_positions(node):
    return isinstance(node, Token)


def run_saved_case(case, artifact):
    if case == 'load':
        with open(artifact, 'rb') as source:
            loaded = Lark.load(source)
        for indices in [[], [7, 49], [0, 63]]:
            text = ''.join('<%d>' % i for i in indices)
            assert loaded.parse(text) == Tree('start', expected_fields(indices))
        assert loaded.parse('<7><49>').meta.end_pos == 7
    elif case == 'standalone':
        namespace = runpy.run_path(artifact)
        loaded = namespace['Lark_StandAlone']()
        result = loaded.parse('<6><43>')
        assert str(result.data) == 'start'
        assert [str(x) if x is not None else None for x in result.children] == [
            '<%d>' % i if i in [6, 43] else None for i in range(64)
        ]
        assert result.meta.end_pos == 7
    else:
        raise AssertionError('unknown test case: ' + case)


class TestOptionalCompilation(unittest.TestCase):
    def test_nullable_group(self):
        for case in ['nullable-group:lalr', 'nullable-group:earley']:
            with self.subTest(case=case):
                backend = case.split(':')[1]
                parser = Lark('start: ([A] | [B]) C\nA: "a"\nB: "b"\nC: "c"', parser=backend)
                for text, first in [('c', None), ('ac', Token('A', 'a')), ('bc', Token('B', 'b'))]:
                    assert parser.parse(text) == Tree('start', [first, Token('C', 'c')])

    def test_duplicate_large(self):
        for case in ['duplicate-large:lalr', 'duplicate-large:earley']:
            with self.subTest(case=case):
                backend = case.split(':')[1]
                fields, definitions = optional_fields(count=13)
                question, _ = optional_fields(False, count=13)
                with self.assertRaises(GrammarError):
                    Lark('start: ' + fields + ' | ' + question + '\n' + definitions, parser=backend)

    def test_unequal_width(self):
        for case in ['unequal-width:lalr', 'unequal-width:earley']:
            with self.subTest(case=case):
                fields, definitions = optional_fields()
                backend = case.split(':')[1]
                parser = Lark(
                    '!start: "a" ["b" | "c" "d"] ' + fields + '\n' + definitions, parser=backend
                )
                for prefix, children in [
                    ('a', ['a', None, None]),
                    ('ab', ['a', 'b']),
                    ('acd', ['a', 'c', 'd']),
                ]:
                    assert parser.parse(prefix).children == children + expected_fields([])
                    assert parser.parse(prefix + '<0><63>').children == children + expected_fields(
                        [0, 63]
                    )

    def test_empty_alternative(self):
        for case in ['empty-alternative:lalr', 'empty-alternative:earley']:
            with self.subTest(case=case):
                backend = case.split(':')[1]
                fields, definitions = optional_fields(count=9)
                for empty_first in (True, False):
                    production = ' | ' + fields if empty_first else fields + ' | '
                    parser = Lark('start: ' + production + '\n' + definitions, parser=backend)
                    assert parser.parse('') == Tree('start', [] if empty_first else [None] * 9)
                    assert parser.parse('<0>') == Tree('start', expected_fields([0], count=9))

    def test_presence(self):
        for case in [
            'presence:lalr:empty',
            'presence:lalr:edges',
            'presence:lalr:mixed',
            'presence:lalr:all',
            'presence:earley:empty',
            'presence:earley:edges',
            'presence:earley:mixed',
            'presence:earley:all',
        ]:
            with self.subTest(case=case):
                fields, definitions = optional_fields()
                grammar = 'start: ' + fields + '\n' + definitions
                _, backend, selection = case.split(':')
                indices = {
                    'empty': [],
                    'edges': [0, 63],
                    'mixed': [2, 19, 47],
                    'all': list(range(64)),
                }[selection]
                parser = Lark(grammar, parser=backend)
                assert parser.parse(''.join('<%d>' % i for i in indices)) == Tree(
                    'start', expected_fields(indices)
                )

    def test_question(self):
        for case in ['question:lalr', 'question:earley']:
            with self.subTest(case=case):
                backend = case.split(':')[1]
                fields, definitions = optional_fields(False)
                parser = Lark('start: ' + fields + '\n' + definitions, parser=backend)
                assert parser.parse('<1><21><62>') == Tree(
                    'start', expected_fields([1, 21, 62], False)
                )
                assert parser.parse('') == Tree('start', [])

    def test_optional_rules(self):
        for case in ['optional-rules:lalr', 'optional-rules:earley']:
            with self.subTest(case=case):
                fields, definitions = optional_fields()
                backend = case.split(':')[1]
                fields = ' '.join('[field%d]' % i for i in range(64))
                definitions += '\n' + '\n'.join('field%d: T%d' % (i, i) for i in range(64))
                parser = Lark('start: ' + fields + '\n' + definitions, parser=backend)
                indices = [0, 32, 63]
                expected = [
                    Tree('field%d' % i, [Token('T%d' % i, '<%d>' % i)]) if i in indices else None
                    for i in range(64)
                ]
                assert parser.parse('<0><32><63>') == Tree('start', expected)
                assert parser.parse('') == Tree('start', [None] * 64)

    def test_grouped_fields(self):
        for case in ['grouped-fields:lalr', 'grouped-fields:earley']:
            with self.subTest(case=case):
                fields, definitions = optional_fields()
                backend = case.split(':')[1]
                fields = ' '.join('[T%d | U%d]' % (i, i) for i in range(64))
                definitions += '\n' + '\n'.join('U%d: "{%d}"' % (i, i) for i in range(64))
                parser = Lark('start: ' + fields + '\n' + definitions, parser=backend)
                expected = expected_fields([0, 63])
                expected[32] = Token('U32', '{32}')
                assert parser.parse('<0>{32}<63>') == Tree('start', expected)
                assert parser.parse('') == Tree('start', [None] * 64)

    def test_selective_positions(self):
        for case in ['selective-positions:lalr', 'selective-positions:earley']:
            with self.subTest(case=case):
                fields, definitions = optional_fields()
                grammar = 'start: ' + fields + '\n' + definitions
                backend = case.split(':')[1]
                parser = Lark(
                    grammar,
                    parser=backend,
                    propagate_positions=lambda value: (
                        isinstance(value, Token) and value.type == 'T32'
                    ),
                )
                result = parser.parse('<0><32><63>')
                assert (result.meta.start_pos, result.meta.end_pos) == (3, 7)
                assert (result.meta.container_start_pos, result.meta.container_end_pos) == (3, 7)
                assert (result.meta.column, result.meta.end_column) == (4, 8)
                assert result.children == expected_fields([0, 32, 63])

    def test_placeholders_off(self):
        fields, definitions = optional_fields()
        grammar = 'start: ' + fields + '\n' + definitions
        parser = Lark(grammar, parser='lalr', maybe_placeholders=False)
        assert parser.parse('<4><37>') == Tree('start', expected_fields([4, 37], False))

    def test_shared_prefix(self):
        fields, definitions = optional_fields()
        parser = Lark('start: A? A ' + fields + '\nA: "a"\n' + definitions, parser='lalr')
        for count in [1, 2]:
            assert parser.parse('a' * count + '<11>').children == [
                Token('A', 'a')
            ] * count + expected_fields([11])

    def test_repeated_symbols(self):
        fields, definitions = optional_fields()
        parser = Lark('start: ' + ' '.join(['A?'] * 64) + '\nA: "a"', parser='lalr')
        for count in [0, 1, 31, 64]:
            assert parser.parse('a' * count).children == [Token('A', 'a')] * count
        with self.assertRaises(UnexpectedInput):
            parser.parse('a' * 65)

    def test_overlapping_placeholders(self):
        fields, definitions = optional_fields()
        parser = Lark(
            'start: ([A] B | B A) ' + fields + '\nA: "a"\nB: "b"\n' + definitions, parser='lalr'
        )
        for text, prefix in [
            ('b', [None, Token('B', 'b')]),
            ('ab', [Token('A', 'a'), Token('B', 'b')]),
            ('ba', [Token('B', 'b'), Token('A', 'a')]),
        ]:
            assert parser.parse(text + '<13>').children == prefix + expected_fields([13])

    def test_alias(self):
        fields, definitions = optional_fields()
        parser = Lark('start: ' + fields + ' -> record\n' + definitions, parser='lalr')
        assert parser.parse('<16>') == Tree('record', expected_fields([16]))

    def test_conditional_inline(self):
        fields, definitions = optional_fields()
        fields, definitions = optional_fields(False)
        parser = Lark('?start: ' + fields + '\n' + definitions, parser='lalr')
        assert parser.parse('<8>') == Token('T8', '<8>')
        assert parser.parse('<8><9>') == Tree('start', expected_fields([8, 9], False))

    def test_underscore_inline(self):
        fields, definitions = optional_fields()
        parser = Lark(
            'start: "[" _fields "]"\n_fields: ' + fields + '\n' + definitions, parser='lalr'
        )
        assert parser.parse('[<7><25>]') == Tree('start', expected_fields([7, 25]))

    def test_templates(self):
        fields, definitions = optional_fields()
        parser = Lark(
            'start: record{T0} ";" record{T1}\nrecord{x}: x ":" ' + fields + '\n' + definitions,
            parser='lalr',
        )
        result = parser.parse('<0>:<3>;<1>:<5>')
        assert [child.children for child in result.children] == [
            [Token('T0', '<0>')] + expected_fields([3]),
            [Token('T1', '<1>')] + expected_fields([5]),
        ]

    def test_repeated_rules(self):
        fields, definitions = optional_fields()
        parser = Lark('start: row+\nrow: "[" ' + fields + ' "]"\n' + definitions, parser='lalr')
        result = parser.parse('[<0>][][<63>]')
        assert result == Tree(
            'start',
            [
                Tree('row', expected_fields([0])),
                Tree('row', expected_fields([])),
                Tree('row', expected_fields([63])),
            ],
        )

    def test_literal_filter(self):
        for case in ['literal-filter:default', 'literal-filter:bang', 'literal-filter:option']:
            with self.subTest(case=case):
                fields, definitions = optional_fields()
                mode = case.split(':')[1]
                prefix = '!start' if mode == 'bang' else 'start'
                literal_fields = ' '.join('["v%d"]' % i for i in range(64))
                parser = Lark(
                    prefix + ': ' + literal_fields + '\n%ignore " "',
                    parser='lalr',
                    keep_all_tokens=mode == 'option',
                )
                result = parser.parse('v0 v12 v63')
                if mode == 'default':
                    assert result == Tree('start', [])
                else:
                    assert [str(x) if x is not None else None for x in result.children] == [
                        'v%d' % i if i in [0, 12, 63] else None for i in range(64)
                    ]

    def test_positions(self):
        for case in ['positions:all', 'positions:filtered']:
            with self.subTest(case=case):
                fields, definitions = optional_fields()
                filtered = case.endswith('filtered')
                parser = Lark(
                    'start: "[" ' + fields + ' "]"\n%ignore /[ \\n]+/\n' + definitions,
                    parser='lalr',
                    propagate_positions=token_positions if filtered else True,
                )
                text = '[\n <1> <28>\n]'
                result = parser.parse(text)
                assert (result.meta.start_pos, result.meta.end_pos) == (0, len(text))
                assert (
                    result.meta.line,
                    result.meta.column,
                    result.meta.end_line,
                    result.meta.end_column,
                ) == (1, 1, 3, 2)
                assert (result.meta.container_start_pos, result.meta.container_end_pos) == (
                    0,
                    len(text),
                )
                assert (result.children[1].start_pos, result.children[28].end_pos) == (3, 11)

    def test_position_filter_inline(self):
        fields, definitions = optional_fields()
        grammar = 'start: ' + fields + '\n' + definitions
        parser = Lark(grammar, parser='lalr', propagate_positions=token_positions)
        result = parser.parse('<3><45>')
        assert (result.meta.start_pos, result.meta.end_pos) == (0, 7)
        assert (result.meta.container_start_pos, result.meta.container_end_pos) == (0, 7)

    def test_transformer_default(self):
        fields, definitions = optional_fields()
        grammar = 'start: ' + fields + '\n' + definitions
        calls = []

        class Build(Transformer):
            def __default__(self, data, children, meta):
                calls.append(str(data))
                return {'kind': str(data), 'values': children}

        parser = Lark(grammar, parser='lalr', transformer=Build())
        assert parser.parse('<2>') == {'kind': 'start', 'values': expected_fields([2])}
        assert calls == ['start']

    def test_transformer_values(self):
        fields, definitions = optional_fields()
        grammar = 'start: ' + fields + '\n' + definitions
        seen = []

        class Build(Transformer):
            def T5(self, token):
                seen.append(token.type)
                return int(token[1:-1])

            def T50(self, token):
                seen.append(token.type)
                return int(token[1:-1])

            def start(self, values):
                return tuple(values)

        parser = Lark(grammar, parser='lalr', transformer=Build())
        assert parser.parse('<5><50>') == tuple(i if i in [5, 50] else None for i in range(64))
        assert seen == ['T5', 'T50']

    def test_custom_tree(self):
        fields, definitions = optional_fields()

        class Record(Tree):
            pass

        parser = Lark(
            'start: row\nrow: ' + fields + '\n' + definitions,
            parser='lalr',
            tree_class=Record,
            propagate_positions=True,
        )
        result = parser.parse('<22>')
        assert type(result) is Record
        assert type(result.children[0]) is Record
        assert result.children[0].children == expected_fields([22])
        assert result.meta.end_pos == 4

    def test_explicit_ambiguity(self):
        fields, definitions = optional_fields()
        parser = Lark(
            'start: (left | right) ' + fields + '\nleft: "x"\nright: "x"\n' + definitions,
            parser='earley',
            ambiguity='explicit',
        )
        result = parser.parse('x<18>')
        assert result.data == '_ambig'
        assert len(result.children) == 2
        assert {child.children[0].data for child in result.children} == {'left', 'right'}
        for child in result.children:
            assert child.data == 'start'
            assert child.children[1:] == expected_fields([18])

    def test_ambiguous_inline(self):
        fields, definitions = optional_fields()
        parser = Lark(
            'start: _choice _choice '
            + fields
            + '\n_choice: left | right\nleft: "x"\nright: "x"\n'
            + definitions,
            parser='earley',
            ambiguity='explicit',
        )
        result = parser.parse('xx<1>')
        assert result.data == '_ambig'
        assert len(result.children) == 4
        assert {
            tuple(child.data for child in branch.children[:2]) for branch in result.children
        } == {('left', 'left'), ('left', 'right'), ('right', 'left'), ('right', 'right')}
        for branch in result.children:
            assert branch.data == 'start'
            assert branch.children[2:] == expected_fields([1])

    def test_priorities_lalr(self):
        fields, definitions = optional_fields()
        for count in [10, 64]:
            fields, definitions = optional_fields(count=count)
            for priority, selected in [('normal', 'high'), ('invert', 'low')]:
                parser = Lark(
                    'start: high | low\nhigh.2: '
                    + fields
                    + '\nlow.1: '
                    + fields
                    + '\n'
                    + definitions,
                    parser='lalr',
                    priority=priority,
                )
                for indices in [[], [1], [0, count - 1]]:
                    result = parser.parse(''.join('<%d>' % i for i in indices))
                    assert result == Tree(
                        'start', [Tree(selected, expected_fields(indices, count=count))]
                    )

    def test_priorities_earley(self):
        fields, definitions = optional_fields()
        for priority, selected in [('normal', 'high'), ('invert', 'low')]:
            parser = Lark(
                'start: high | low\nhigh.2: LONG '
                + fields
                + '\nlow.1: '
                + ' '.join(['A'] * 8)
                + ' '
                + fields
                + '\nLONG: "aaaaaaaa"\nA: "a"\n'
                + definitions,
                parser='earley',
                ambiguity='resolve',
                priority=priority,
            )
            prefix = [Token('LONG', 'aaaaaaaa')] if selected == 'high' else [Token('A', 'a')] * 8
            for indices in [[], [1], [0, 63]]:
                result = parser.parse('aaaaaaaa' + ''.join('<%d>' % i for i in indices))
                assert result == Tree('start', [Tree(selected, prefix + expected_fields(indices))])

    def test_duplicate_ambiguity(self):
        fields, definitions = optional_fields()
        parser = Lark(
            'start: ' + ' '.join(['A?'] * 32) + '\nA: "a"', parser='earley', ambiguity='explicit'
        )
        assert parser.parse('aaa') == Tree('start', [Token('A', 'a')] * 3)

    def test_duplicate_error(self):
        for case in [
            'duplicate-error:placeholders',
            'duplicate-error:aliases',
            'duplicate-error:aliases-earley',
        ]:
            with self.subTest(case=case):
                fields, definitions = optional_fields()
                variant = case.split(':')[1]
                if variant == 'placeholders':
                    bad = 'start: [A] [A] ' + fields + '\nA: "a"\n' + definitions
                else:
                    bad = (
                        'start: ' + fields + ' -> one\n     | ' + fields + ' -> two\n' + definitions
                    )
                with self.assertRaises(GrammarError):
                    Lark(bad, parser='earley' if variant == 'aliases-earley' else 'lalr')

    def test_reuse(self):
        fields, definitions = optional_fields()
        grammar = 'start: ' + fields + '\n' + definitions
        parser = Lark(grammar, parser='lalr')
        for invalid in ['<4><3>', '<3><3>', '<64>']:
            with self.assertRaises(UnexpectedInput):
                parser.parse(invalid)
            assert parser.parse('<0><63>') == Tree('start', expected_fields([0, 63]))
        assert parser.parse('') == Tree('start', expected_fields([]))

    def test_load(self):
        case = 'load'
        fields, definitions = optional_fields()
        grammar = 'start: ' + fields + '\n' + definitions
        parser = Lark(grammar, parser='lalr', propagate_positions=True)
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / 'parser.bin'
            with artifact.open('wb') as output:
                parser.save(output)
            subprocess.run(
                [sys.executable, '-m', 'tests.test_optional_compilation', case, str(artifact)],
                check=True,
            )

    def test_standalone(self):
        case = 'standalone'
        fields, definitions = optional_fields()
        grammar = 'start: ' + fields + '\n' + definitions
        from lark.tools.standalone import gen_standalone

        parser = Lark(grammar, parser='lalr', propagate_positions=True)
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / 'parser.py'
            with artifact.open('w', encoding='utf-8') as output:
                gen_standalone(parser, out=output)
            subprocess.run(
                [sys.executable, '-m', 'tests.test_optional_compilation', case, str(artifact)],
                check=True,
            )

    def test_cyk_nonempty_production(self):
        fields, definitions = optional_fields(count=10)
        parser = Lark('start: "!" ' + fields + '\n' + definitions, parser='cyk')
        for indices in ([], [0], [0, 9], list(range(10))):
            with self.subTest(indices=indices):
                text = '!' + ''.join('<%d>' % index for index in indices)
                self.assertEqual(parser.parse(text),
                                 Tree('start', expected_fields(indices, count=10)))

    def test_compiled_grammar_size(self):
        # Ten independent optionals previously produced 2**10 start rules.
        for backend in ('lalr', 'earley'):
            with self.subTest(parser=backend):
                fields, definitions = optional_fields(count=10)
                parser = Lark('start: ' + fields + '\n' + definitions, parser=backend)
                self.assertLess(len(parser.rules), 200)
                self.assertEqual(
                    parser.parse('<0><9>'), Tree('start', expected_fields([0, 9], count=10))
                )


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] in ('load', 'standalone'):
        run_saved_case(sys.argv[1], sys.argv[2])
    else:
        unittest.main()
