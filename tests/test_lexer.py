from unittest import TestCase, main

from lark import Lark, Tree, TextSlice
from lark.exceptions import GrammarError


class TestLexer(TestCase):
    def setUp(self):
        pass

    def test_basic(self):
        p = Lark("""
            start: "a" "b" "c" "d"
            %ignore " "
        """)

        res = list(p.lex("abc cba dd"))
        assert res == list('abccbadd')

        res = list(p.lex("abc cba dd", dont_ignore=True))
        assert res == list('abc cba dd')

    def test_flag_order_is_deterministic(self):
        # Two or more flags on one terminal is the only case where order exists; the
        # other flag tests all use a single flag. Without sorting, the frozenset is
        # iterated in hash order and the regexp differs between processes.
        p = Lark('start: A+\nA: /x/imsu\n', parser='lalr')
        self.assertEqual([t.pattern.to_regexp() for t in p.terminals],
                         ['(?u:(?s:(?m:(?i:x))))'])

    def test_flag_order_with_new_flags(self):
        # Test that new flags (a, L) work and are sorted deterministically
        p = Lark('start: A+\nA: /x/ai\n', parser='lalr')
        # Flags should be sorted alphabetically: a before i
        self.assertEqual([t.pattern.to_regexp() for t in p.terminals],
                         ['(?i:(?a:x))'])

        # 'L' sorts before 'a' (ASCII order), and requires use_bytes
        p = Lark('start: A+\nA: /x/aL\n', parser='lalr', use_bytes=True)
        self.assertEqual([t.pattern.to_regexp() for t in p.terminals],
                         ['(?a:(?L:x))'])

    def test_conflicting_ascii_unicode_flags(self):
        # 'a' (ASCII) and 'u' (UNICODE) are mutually exclusive
        self.assertRaises(GrammarError, Lark, 'start: A+\nA: /x/au\n', parser='lalr')

    def test_subset_lex(self):
        p = Lark("""
            start: "a" "b" "c" "d"
            %ignore " "
        """)

        res = list(p.lex(TextSlice("xxxabc cba ddxx", 3, -2)))
        assert res == list('abccbadd')

        res = list(p.lex(TextSlice("aaaabc cba dddd", 3, -2)))
        assert res == list('abccbadd')


if __name__ == '__main__':
    main()
