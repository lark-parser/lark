from __future__ import absolute_import

import sys
from unittest import TestCase, main

from lark import Lark, Token, Tree
from lark.load_grammar import GrammarError, GRAMMAR_ERRORS, find_grammar_errors
from lark.load_grammar import FromPackageLoader


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

    def test_override_rule(self):
        # Overrides the 'sep' template in existing grammar to add an optional terminating delimiter
        # Thus extending it beyond its original capacity
        p = Lark("""
            %import .test_templates_import (start, sep)

            %override sep{item, delim}: item (delim item)* delim?
            %ignore " "
        """, source_path=__file__)

        a = p.parse('[1, 2, 3]')
        b = p.parse('[1, 2, 3, ]')
        assert a == b

        self.assertRaises(GrammarError, Lark, """
            %import .test_templates_import (start, sep)

            %override sep{item}: item (delim item)* delim?
        """)

        self.assertRaises(GrammarError, Lark, """
            %override sep{item}: item (delim item)* delim?
        """)

    def test_override_terminal(self):
        p = Lark("""

            %import .grammars.ab (startab, A, B)

            %override A: "c"
            %override B: "d"
        """, start='startab', source_path=__file__)

        a = p.parse('cd')
        self.assertEqual(a.children[0].children, [Token('A', 'c'), Token('B', 'd')])

    def test_extend_rule(self):
        p = Lark("""
            %import .grammars.ab (startab, A, B, expr)

            %extend expr: B A
        """, start='startab', source_path=__file__)
        a = p.parse('abab')
        self.assertEqual(a.children[0].children, ['a', Tree('expr', ['b', 'a']), 'b'])

        self.assertRaises(GrammarError, Lark, """
            %extend expr: B A
        """)

    def test_extend_term(self):
        p = Lark("""
            %import .grammars.ab (startab, A, B, expr)

            %extend A: "c"
        """, start='startab', source_path=__file__)
        a = p.parse('acbb')
        self.assertEqual(a.children[0].children, ['a', Tree('expr', ['c', 'b']), 'b'])

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

    def test_import_custom_sources(self):
        custom_loader = FromPackageLoader('tests', ('grammars', ))

        grammar = """
        start: startab

        %import ab.startab
        """

        p = Lark(grammar, import_paths=[custom_loader])
        self.assertEqual(p.parse('ab'),
                            Tree('start', [Tree('startab', [Tree('ab__expr', [Token('ab__A', 'a'), Token('ab__B', 'b')])])]))

    def test_import_custom_sources2(self):
        custom_loader = FromPackageLoader('tests', ('grammars', ))

        grammar = """
        start: rule_to_import

        %import test_relative_import_of_nested_grammar__grammar_to_import.rule_to_import
        """
        p = Lark(grammar, import_paths=[custom_loader])
        x = p.parse('N')
        self.assertEqual(next(x.find_data('rule_to_import')).children, ['N'])

    def test_import_custom_sources3(self):
        custom_loader2 = FromPackageLoader('tests')
        grammar = """
        %import .test_relative_import (start, WS)
        %ignore WS
        """
        p = Lark(grammar, import_paths=[custom_loader2], source_path=__file__) # import relative to current file
        x = p.parse('12 capybaras')
        self.assertEqual(x.children, ['12', 'capybaras'])

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



if __name__ == '__main__':
    main()



