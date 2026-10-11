from unittest import TestCase, main
import re

from lark import Lark, Tree, TextSlice, UnexpectedCharacters


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

    def test_global_dotall_positions(self):
        grammar = 'start: MULTILINE BANG\nMULTILINE: /a.*?b/\nBANG: "!"'
        for lexer in ('basic', 'contextual'):
            for use_bytes in (False, True):
                for flags in (re.DOTALL, re.DOTALL | re.IGNORECASE):
                    p = Lark(grammar, parser='lalr', lexer=lexer,
                             use_bytes=use_bytes, g_regex_flags=flags,
                             propagate_positions=True)
                    for text in ('a\nb!', 'a\n\nb!', 'a\r\nb!'):
                        with self.subTest(lexer=lexer, use_bytes=use_bytes,
                                          flags=flags, text=text):
                            line = text.count('\n') + 1
                            tree = p.parse(text.encode() if use_bytes else text)
                            multiline, bang = tree.children
                            self.assertEqual((multiline.line, multiline.column), (1, 1))
                            self.assertEqual((multiline.end_line, multiline.end_column), (line, 2))
                            self.assertEqual((bang.line, bang.column), (line, 2))
                            self.assertEqual((bang.end_line, bang.end_column), (line, 3))
                            self.assertEqual((bang.start_pos, bang.end_pos), (len(text) - 1, len(text)))
                            self.assertEqual((tree.meta.end_line, tree.meta.end_column), (line, 3))

    def test_global_dotall_ignored_positions(self):
        grammar = 'start: BANG\nBANG: "!"\n%ignore /a.*?b/'
        for lexer in ('basic', 'contextual'):
            for use_bytes in (False, True):
                with self.subTest(lexer=lexer, use_bytes=use_bytes):
                    p = Lark(grammar, parser='lalr', lexer=lexer,
                             use_bytes=use_bytes, g_regex_flags=re.DOTALL,
                             propagate_positions=True)
                    tree = p.parse(b'a\nb!' if use_bytes else 'a\nb!')
                    bang, = tree.children
                    self.assertEqual((bang.line, bang.column), (2, 2))
                    self.assertEqual((tree.meta.line, tree.meta.column), (2, 2))

    def test_global_dotall_error_position(self):
        grammar = 'start: MULTILINE "!"\nMULTILINE: /a.*?b/'
        for lexer in ('basic', 'contextual'):
            with self.subTest(lexer=lexer):
                p = Lark(grammar, parser='lalr', lexer=lexer, g_regex_flags=re.DOTALL)
                with self.assertRaises(UnexpectedCharacters) as cm:
                    p.parse('a\nb?')
                self.assertEqual((cm.exception.line, cm.exception.column), (2, 2))


if __name__ == '__main__':
    main()
