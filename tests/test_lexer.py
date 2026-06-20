import copy
import pickle
from unittest import TestCase, main

from lark import Lark, Tree, TextSlice
from lark.lexer import Token


class TestLexer(TestCase):
    def setUp(self):
        pass

    def test_token_copy_preserves_end_position(self):
        # deepcopy/copy/pickle round-trips must keep the end_* position
        # attributes, like new_borrow_pos does, instead of dropping them.
        t = Token("WORD", "hello", start_pos=0, line=1, column=1,
                  end_line=2, end_column=6, end_pos=5)
        attrs = ("type", "value", "start_pos", "line", "column",
                 "end_line", "end_column", "end_pos")
        expected = [getattr(t, a) for a in attrs]
        for copied in (copy.deepcopy(t), copy.copy(t), pickle.loads(pickle.dumps(t))):
            self.assertEqual([getattr(copied, a) for a in attrs], expected)

    def test_basic(self):
        p = Lark("""
            start: "a" "b" "c" "d"
            %ignore " "
        """)

        res = list(p.lex("abc cba dd"))
        assert res == list('abccbadd')

        res = list(p.lex("abc cba dd", dont_ignore=True))
        assert res == list('abc cba dd')

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
