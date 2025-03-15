from __future__ import absolute_import

import os
from unittest import TestCase, main
from .configurations import import_test

from lark import Lark, Token, Tree, ParseError, UnexpectedInput
from lark.load_grammar import GrammarError, GRAMMAR_ERRORS, find_grammar_errors, list_grammar_imports
from lark.load_grammar import FromPackageLoader
from lark.grammar import Symbol

class TestGrammar(TestCase):
    def setUp(self):
        pass

    def test_errors(self):
        for msg, examples in GRAMMAR_ERRORS:
            for example in examples:
                try:
                    p = Lark(example)
                except GrammarError as e:
                    assert msg in str(e)
                else:
                    assert False, "example did not raise an error"

    def test_empty_literal(self):
        # Issues #888
        self.assertRaises(GrammarError, Lark, "start: \"\"")

    def test_ignore_name(self):
        spaces = []
        p = Lark("""
            start: "a" "b"
            WS: " "
            %ignore WS
        """, parser='lalr', lexer_callbacks={'WS': spaces.append})
        assert p.parse("a b") == p.parse("a    b")
        assert len(spaces) == 5


    def test_override_rule(self):
        # Overrides the 'sep' template in existing grammar to add an optional terminating delimiter
        # Thus extending it beyond its original capacity
        p = Lark("""
            %import .test_templates_import.sep
            %import .test_templates_import.start -> _start
            start: _start

            %override sep{item, delim}: item (delim item)* delim?
            %ignore " "
        """, source_path=__file__)

        a = p.parse('[1, 2, 3]')
        b = p.parse('[1, 2, 3, ]')
        assert a == b

        self.assertRaises(GrammarError, Lark, """
            %import .test_templates_import.sep
            %import .test_templates_import.start -> _start
            start: _start

            %override sep{item}: item (delim item)* delim?
        """, source_path=__file__)

        self.assertRaises(GrammarError, Lark, """
            %override sep{item}: item (delim item)* delim?
        """, source_path=__file__)

    @import_test
    def test_override_terminal(self, test_type: str):
        p = Lark("""

            %import .grammars.ab (startab, A, B)

            start: startab

            %override A: "c"
            %override B: "d"
        """, start='start', source_path=__file__, legacy_import=(test_type == "legacy"))

        a = p.parse('cd')

        expected = [
            Tree('grammars__ab__expr', [
                Token('grammars__ab__A', 'c'),
                Token('grammars__ab__B', 'd')
            ])
        ] if test_type == "new" else [
            Tree('grammars__ab__expr', [
                Token(Token('TERMINAL', 'A'), 'c'),
                Token(Token('TERMINAL', 'B'), 'd')
            ])
        ]

        self.assertEqual(a.children[0].children, expected)

    @import_test
    def test_extend_rule(self, test_type: str):
        p = Lark("""
            %import .grammars.ab (startab, A, B, expr)

            start: startab

            %extend expr: B A
        """, start='start', source_path=__file__, legacy_import=(test_type == "legacy"))
        a = p.parse('abab')

        expected = [
            Tree('grammars__ab__expr', [
                Token('grammars__ab__A', 'a'),
                Tree('grammars__ab__expr', [
                    Token('grammars__ab__B', 'b'),
                    Token('grammars__ab__A', 'a')
                ]),
                Token('grammars__ab__B', 'b')
            ])
        ] if test_type == "new" else [
            Tree(Token('RULE', 'expr'), [
                Token(Token('TERMINAL', 'A'), 'a'),
                Tree(Token('RULE', 'expr'), [
                    Token('B', 'b'),
                    Token('A', 'a')
                ]),
                Token(Token('TERMINAL', 'B'), 'b')
            ])
        ]

        self.assertEqual(a.children[0].children, expected)

        self.assertRaises(GrammarError, Lark, """
            %extend expr: B A
        """)

    @import_test
    def test_extend_term(self, test_type: str):
        p = Lark("""
            %import .grammars.ab (startab, A, B, expr)

            start: startab

            %extend A: "c"
        """, start='start', source_path=__file__, legacy_import=(test_type == "legacy"))
        a = p.parse('acbb')

        expected = [
            Tree('grammars__ab__expr', [
                Token('grammars__ab__A', 'a'),
                Tree('grammars__ab__expr', [
                    Token('grammars__ab__A', 'c'),
                    Token('grammars__ab__B', 'b')
                ]),
                Token('grammars__ab__B', 'b')
            ])
        ] if test_type == "new" else [
            Tree(Token('RULE', 'expr'), [
                Token(Token('TERMINAL', 'A'), 'a'),
                Tree(Token('RULE', 'expr'), [
                    Token(Token('TERMINAL', 'A'), 'c'),
                    Token(Token('TERMINAL', 'B'), 'b')
                ]),
                Token(Token('TERMINAL', 'B'), 'b')
            ])
        ]

        self.assertEqual(a.children[0].children, expected)

    def test_extend_twice(self):
        p = Lark("""
            start: x+

            x: "a"
            %extend x: "b"
            %extend x: "c"
        """)

        assert p.parse("abccbba") == p.parse("cbabbbb")

    def test_undefined_ignore(self):
        g = """!start: "A"

            %ignore B
            """
        self.assertRaises( GrammarError, Lark, g)

        g = """!start: "A"

            %ignore start
            """
        self.assertRaises( GrammarError, Lark, g)

    def test_alias_in_terminal(self):
        g = """start: TERM
            TERM: "a" -> alias
            """
        self.assertRaises( GrammarError, Lark, g)

    def test_undefined_rule(self):
        self.assertRaises(GrammarError, Lark, """start: a""")

    def test_undefined_term(self):
        self.assertRaises(GrammarError, Lark, """start: A""")

    def test_token_multiline_only_works_with_x_flag(self):
        g = r"""start: ABC
                ABC: /  a      b c
                            d
                            e f
                        /i
                    """
        self.assertRaises( GrammarError, Lark, g)

    @import_test
    def test_import_custom_sources(self, test_type: str):
        custom_loader = FromPackageLoader(__name__, ('grammars', ))

        grammar = """
        start: startab

        %import ab.startab
        """

        p = Lark(grammar, import_paths=[custom_loader], legacy_import=(test_type == "legacy"))

        expected = Tree(Token('RULE', 'start'), [
            Tree('ab__startab', [
                Tree('ab__expr', [
                    Token('ab__A', 'a'),
                    Token('ab__B', 'b')
                ])
            ])
        ]) if test_type == "new" else Tree('start', [
            Tree('startab', [
                Tree('ab__expr', [
                    Token('ab__A', 'a'),
                    Token('ab__B', 'b')
                ])
            ])
        ])

        self.assertEqual(p.parse('ab'), expected)

    @import_test
    def test_import_custom_sources2(self, test_type: str):
        custom_loader = FromPackageLoader(__name__, ('grammars', ))

        grammar = """
        start: rule_to_import

        %import test_relative_import_of_nested_grammar__grammar_to_import.rule_to_import
        """
        p = Lark(grammar, import_paths=[custom_loader], legacy_import=(test_type == "legacy"))
        x = p.parse('N')

        if test_type == "new":
            self.assertEqual(next(x.find_data('test_relative_import_of_nested_grammar__grammar_to_import__rule_to_import')).children, ['N'])
        else:
            self.assertEqual(next(x.find_data('rule_to_import')).children, ['N'])

    @import_test
    def test_import_custom_sources3(self, test_type: str):
        custom_loader2 = FromPackageLoader(__name__)
        grammar = """
        %import .test_relative_import.WS
        %import .test_relative_import.start -> _start
        start: _start
        %ignore WS
        """
        p = Lark(grammar, import_paths=[custom_loader2], source_path=__file__, legacy_import=(test_type == "legacy")) # import relative to current file
        x = p.parse('12 capybaras')
        if test_type == "new":
            self.assertEqual(x.children, [Tree('test_relative_import__start', [Token('test_relative_import__grammars__test__NUMBER', '12'), Token('test_relative_import__common__WORD', 'capybaras')])])
        else:
            self.assertEqual(x.children, [Token('test_relative_import__NUMBER', '12'), Token('test_relative_import__WORD', 'capybaras')])

    def test_find_grammar_errors(self):
        text = """
        a: rule
        b rule
        c: rule
        B.: "hello" f
        D: "okay"
        """

        assert [e.line for e, _s in find_grammar_errors(text)] == [3, 5]

        text = """
        a: rule
        b rule
        | ok
        c: rule
        B.: "hello" f
        D: "okay"
        """

        assert [e.line for e, _s in find_grammar_errors(text)] == [3, 4, 6]

        text = """
        a: rule @#$#@$@&&
        b: rule
        | ok
        c: rule
        B: "hello" f @
        D: "okay"
        """

        x = find_grammar_errors(text)
        assert [e.line for e, _s in find_grammar_errors(text)] == [2, 6]

    def test_ranged_repeat_terms(self):
        g = u"""!start: AAA
                AAA: "A"~3
            """
        l = Lark(g, parser='lalr')
        self.assertEqual(l.parse(u'AAA'), Tree('start', ["AAA"]))
        self.assertRaises((ParseError, UnexpectedInput), l.parse, u'AA')
        self.assertRaises((ParseError, UnexpectedInput), l.parse, u'AAAA')

        g = u"""!start: AABB CC
                AABB: "A"~0..2 "B"~2
                CC: "C"~1..2
            """
        l = Lark(g, parser='lalr')
        self.assertEqual(l.parse(u'AABBCC'), Tree('start', ['AABB', 'CC']))
        self.assertEqual(l.parse(u'BBC'), Tree('start', ['BB', 'C']))
        self.assertEqual(l.parse(u'ABBCC'), Tree('start', ['ABB', 'CC']))
        self.assertRaises((ParseError, UnexpectedInput), l.parse, u'AAAB')
        self.assertRaises((ParseError, UnexpectedInput), l.parse, u'AAABBB')
        self.assertRaises((ParseError, UnexpectedInput), l.parse, u'ABB')
        self.assertRaises((ParseError, UnexpectedInput), l.parse, u'AAAABB')

    def test_ranged_repeat_large(self):
        g = u"""!start: "A"~60
            """
        l = Lark(g, parser='lalr')
        self.assertGreater(len(l.rules), 1, "Expected that more than one rule will be generated")
        self.assertEqual(l.parse(u'A' * 60), Tree('start', ["A"] * 60))
        self.assertRaises(ParseError, l.parse, u'A' * 59)
        self.assertRaises((ParseError, UnexpectedInput), l.parse, u'A' * 61)

        g = u"""!start: "A"~15..100
            """
        l = Lark(g, parser='lalr')
        for i in range(0, 110):
            if 15 <= i <= 100:
                self.assertEqual(l.parse(u'A' * i), Tree('start', ['A']*i))
            else:
                self.assertRaises(UnexpectedInput, l.parse, u'A' * i)

        # 8191 is a Mersenne prime
        g = u"""start: "A"~8191
            """
        l = Lark(g, parser='lalr')
        self.assertEqual(l.parse(u'A' * 8191), Tree('start', []))
        self.assertRaises(UnexpectedInput, l.parse, u'A' * 8190)
        self.assertRaises(UnexpectedInput, l.parse, u'A' * 8192)

    def test_large_terminal(self):
        g = "start: NUMBERS\n"
        g += "NUMBERS: " + '|'.join('"%s"' % i for i in range(0, 1000))

        l = Lark(g, parser='lalr')
        for i in (0, 9, 99, 999):
            self.assertEqual(l.parse(str(i)), Tree('start', [str(i)]))
        for i in (-1, 1000):
            self.assertRaises(UnexpectedInput, l.parse, str(i))

    def test_list_grammar_imports(self):
            grammar = """
            %import .test_templates_import (start, sep)

            %override sep{item, delim}: item (delim item)* delim?
            %ignore " "
            """

            imports = list_grammar_imports(grammar, [os.path.dirname(__file__)])
            self.assertEqual({os.path.split(i)[-1] for i in imports}, {'test_templates_import.lark', 'templates.lark'})

            imports = list_grammar_imports('%import common.WS', [])
            assert len(imports) == 1 and imports[0].pkg_name == 'lark'

    def test_inline_with_expand_single(self):
        grammar = r"""
        start: _a
        !?_a: "A"
        """
        self.assertRaises(GrammarError, Lark, grammar)


    def test_line_breaks(self):
        p = Lark(r"""start: "a" \
                       "b"
                """)
        p.parse('ab')


    def test_symbol_eq(self):
        a = None
        b = Symbol("abc")

        self.assertNotEqual(a, b)


if __name__ == '__main__':
    main()
