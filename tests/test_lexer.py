from unittest import TestCase, main

from lark import Lark, Tree, TextSlice, Token


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

    def test_token_comparisons(self):
        token = Token('NAME', 'foo')
        for other, equal in [
            (Token('NAME', 'foo'), True),
            (Token('OTHER', 'foo'), False),
            (Token('NAME', 'bar'), False),
            (Token('OTHER', 'bar'), False),
            ('foo', True),
            ('bar', False),
            (None, False),
            (123, False),
        ]:
            with self.subTest(other=other):
                self.assertIs(token == other, equal)
                self.assertIs(other == token, equal)
                self.assertIs(token != other, not equal)
                self.assertIs(other != token, not equal)

    def test_token_comparison_ignores_positions(self):
        first = Token('NAME', 'foo', 0, 1, 1, 1, 4, 3)
        second = Token('NAME', 'foo', 5, 2, 1, 2, 4, 8)
        self.assertEqual(first, second)
        self.assertFalse(first != second)
        self.assertEqual(hash(first), hash(second))
        self.assertEqual(hash(first), hash('foo'))
        self.assertEqual({first: 'value'}[second], 'value')
        self.assertEqual({first: 'value'}['foo'], 'value')

    def test_token_comparison_not_implemented(self):
        token = Token('NAME', 'foo')
        self.assertIs(token.__eq__(None), NotImplemented)
        self.assertIs(token.__ne__(None), NotImplemented)

        equal, unequal = object(), object()

        class ReflectedComparison:
            def __eq__(self, other):
                return equal

            def __ne__(self, other):
                return unequal

        other = ReflectedComparison()
        self.assertIs(token == other, equal)
        self.assertIs(token != other, unequal)
        self.assertIs(other == token, equal)
        self.assertIs(other != token, unequal)

    def test_token_comparison_subclass(self):
        class UnequalToken(Token):
            def __eq__(self, other):
                return False

        token = Token('NAME', 'foo')
        other = UnequalToken('NAME', 'foo')
        self.assertFalse(token == other)
        self.assertFalse(other == token)
        self.assertTrue(token != other)
        self.assertTrue(other != token)

    def test_filter_tokens_by_type_and_value(self):
        parser = Lark('''
            start: KEYWORD NAME
            KEYWORD: "if"
            NAME: /[a-z]+/
            %ignore " "
        ''', parser='lalr')
        tokens = parser.parse('if if').children
        keyword = Token('KEYWORD', 'if')
        self.assertEqual(tokens, [keyword, Token('NAME', 'if')])
        self.assertEqual([token for token in tokens if token != keyword],
                         [Token('NAME', 'if')])


if __name__ == '__main__':
    main()
