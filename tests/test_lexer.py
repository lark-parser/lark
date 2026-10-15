from unittest import TestCase, main

from lark import Lark, Tree, TextSlice


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

    def test_subset_lex(self):
        p = Lark("""
            start: "a" "b" "c" "d"
            %ignore " "
        """)

        res = list(p.lex(TextSlice("xxxabc cba ddxx", 3, -2)))
        assert res == list('abccbadd')

        res = list(p.lex(TextSlice("aaaabc cba dddd", 3, -2)))
        assert res == list('abccbadd')

    def test_make_joined_pattern_preserves_flags(self):
        """Regression test: combined terminals must preserve their flags."""
        parser = Lark('start: A\nA: "ab"i "cd"i', parser='lalr')
        terminal = next(t for t in parser.terminals if t.name == 'A')
        assert terminal.pattern.flags == frozenset({'i'}), \
            "flags were dropped on joined pattern"

    def test_make_joined_pattern_with_disjoint_flags(self):
        """Joined pattern with no common flags should report an empty set."""
        parser = Lark('start: A\nA: /a/i /b/s /c/m', parser='lalr')
        terminal = next(t for t in parser.terminals if t.name == 'A')
        assert terminal.pattern.flags == frozenset()
        # Each sub-pattern's inline flags still govern its own matching.
        regexp = terminal.pattern.to_regexp()
        assert '?i:' in regexp
        assert '?s:' in regexp
        assert '?m:' in regexp


if __name__ == '__main__':
    main()