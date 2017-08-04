from __future__ import absolute_import

import unittest
import logging
import os
import sys
try:
    from cStringIO import StringIO as cStringIO
except ImportError:
    # Available only in Python 2.x, 3.x only has io.StringIO from below
    cStringIO = None
from io import (
        StringIO as uStringIO,
        open,
    )

logging.basicConfig(level=logging.INFO)

from lark.lark import Lark
from lark.common import GrammarError, ParseError
from lark.lexer import LexError
from lark.tree import Tree

__path__ = os.path.dirname(__file__)
def _read(n, *args):
    with open(os.path.join(__path__, n), *args) as f:
        return f.read()

class TestParsers(unittest.TestCase):
    def test_same_ast(self):
        "Tests that Earley and LALR parsers produce equal trees"
        g = Lark("""start: "(" name_list ("," "*" NAME)? ")"
                    name_list: NAME | name_list "," NAME
                    NAME: /\w+/ """, parser='lalr')
        l = g.parse('(a,b,c,*x)')

        g = Lark("""start: "(" name_list ("," "*" NAME)? ")"
                    name_list: NAME | name_list "," NAME
                    NAME: /\w/+ """)
        l2 = g.parse('(a,b,c,*x)')
        assert l == l2, '%s != %s' % (l.pretty(), l2.pretty())

    def test_infinite_recurse(self):
        g = """start: a
               a: a | "a"
            """

        self.assertRaises(GrammarError, Lark, g, parser='lalr')

        l = Lark(g, parser='earley')
        self.assertRaises(ParseError, l.parse, 'a')


def _make_full_earley_test(LEXER):
    class _TestFullEarley(unittest.TestCase):
        def test_anon_in_scanless(self):
            # Fails an Earley implementation without special handling for empty rules,
            # or re-processing of already completed rules.
            g = Lark(r"""start: B
                         B: ("ab"|/[^b]/)*
                      """, lexer=LEXER)

            self.assertEqual( g.parse('abc').children[0], 'abc')

        def test_earley_scanless(self):
            g = Lark("""start: A "b" c
                        A: "a"+
                        c: "abc"
                        """, parser="earley", lexer=LEXER)
            x = g.parse('aaaababc')

        def test_earley_scanless2(self):
            grammar = """
            start: statement+

            statement: "r"
                     | "c" /[a-z]/+

            %ignore " "
            """

            program = """c b r"""

            l = Lark(grammar, parser='earley', lexer=LEXER)
            l.parse(program)

        def test_earley_scanless3(self):
            "Tests prioritization and disambiguation for pseudo-terminals (there should be only one result)"

            grammar = """
            start: A A
            A: "a"+
            """

            l = Lark(grammar, parser='earley', lexer=LEXER)
            res = l.parse("aaa")
            self.assertEqual(res.children, ['aa', 'a'])

        def test_earley_scanless4(self):
            grammar = """
            start: A A?
            A: "a"+
            """

            l = Lark(grammar, parser='earley', lexer=LEXER)
            res = l.parse("aaa")
            self.assertEqual(res.children, ['aaa'])

        def test_earley_repeating_empty(self):
            # This was a sneaky bug!

            grammar = """
            !start: "a" empty empty "b"
            empty: empty2
            empty2:
            """

            parser = Lark(grammar, parser='earley', lexer=LEXER)
            res = parser.parse('ab')

            empty_tree = Tree('empty', [Tree('empty2', [])])
            self.assertSequenceEqual(res.children, ['a', empty_tree, empty_tree, 'b'])

        def test_earley_explicit_ambiguity(self):
            # This was a sneaky bug!

            grammar = """
            start: a b | ab
            a: "a"
            b: "b"
            ab: "ab"
            """

            parser = Lark(grammar, parser='earley', lexer=LEXER, ambiguity='explicit')
            res = parser.parse('ab')

            self.assertEqual( res.data, '_ambig')
            self.assertEqual( len(res.children), 2)

    _NAME = "TestFullEarley" + (LEXER or 'Scanless').capitalize()
    _TestFullEarley.__name__ = _NAME
    globals()[_NAME] = _TestFullEarley


def _make_parser_test(LEXER, PARSER):
    def _Lark(grammar, **kwargs):
        return Lark(grammar, lexer=LEXER, parser=PARSER, **kwargs)
    class _TestParser(unittest.TestCase):
        def test_basic1(self):
            g = _Lark("""start: a+ b a* "b" a*
                        b: "b"
                        a: "a"
                     """)

            r = g.parse('aaabaab')
            self.assertEqual( ''.join(x.data for x in r.children), 'aaabaa' )
            r = g.parse('aaabaaba')
            self.assertEqual( ''.join(x.data for x in r.children), 'aaabaaa' )

            self.assertRaises(ParseError, g.parse, 'aaabaa')

        def test_basic2(self):
            # Multiple parsers and colliding tokens
            g = _Lark("""start: B A
                         B: "12"
                         A: "1" """)
            g2 = _Lark("""start: B A
                         B: "12"
                         A: "2" """)
            x = g.parse('121')
            assert x.data == 'start' and x.children == ['12', '1'], x
            x = g2.parse('122')
            assert x.data == 'start' and x.children == ['12', '2'], x


        @unittest.skipIf(cStringIO is None, "cStringIO not available")
        def test_stringio_bytes(self):
            """Verify that a Lark can be created from file-like objects other than Python's standard 'file' object"""
            _Lark(cStringIO(b'start: a+ b a* "b" a*\n b: "b"\n a: "a" '))

        def test_stringio_unicode(self):
            """Verify that a Lark can be created from file-like objects other than Python's standard 'file' object"""
            _Lark(uStringIO(u'start: a+ b a* "b" a*\n b: "b"\n a: "a" '))

        def test_unicode(self):
            g = _Lark(u"""start: UNIA UNIB UNIA
                        UNIA: /\xa3/
                        UNIB: /\u0101/
                        """)
            g.parse(u'\xa3\u0101\u00a3')

        @unittest.skipIf(LEXER is None, "Regexps >1 not supported with scanless parsing")
        def test_unicode2(self):
            g = _Lark(r"""start: UNIA UNIB UNIA UNIC
                        UNIA: /\xa3/
                        UNIB: "a\u0101b\ "
                        UNIC: /a?\u0101c\n/
                        """)
            g.parse(u'\xa3a\u0101b\\ \u00a3\u0101c\n')

        def test_unicode3(self):
            g = _Lark(r"""start: UNIA UNIB UNIA UNIC
                        UNIA: /\xa3/
                        UNIB: "\u0101"
                        UNIC: /\u0203/ /\n/
                        """)
            g.parse(u'\xa3\u0101\u00a3\u0203\n')


        def test_stack_for_ebnf(self):
            """Verify that stack depth isn't an issue for EBNF grammars"""
            g = _Lark(r"""start: a+
                         a : "a" """)

            g.parse("a" * (sys.getrecursionlimit()*2 ))

        def test_expand1_lists_with_one_item(self):
            g = _Lark(r"""start: list
                            ?list: item+
                            item : A
                            A: "a"
                        """)
            r = g.parse("a")

            # because 'list' is an expand-if-contains-one rule and we only provided one element it should have expanded to 'item'
            self.assertSequenceEqual([subtree.data for subtree in r.children], ('item',))

            # regardless of the amount of items: there should be only *one* child in 'start' because 'list' isn't an expand-all rule
            self.assertEqual(len(r.children), 1)

        def test_expand1_lists_with_one_item_2(self):
            g = _Lark(r"""start: list
                            ?list: item+ "!"
                            item : A
                            A: "a"
                        """)
            r = g.parse("a!")

            # because 'list' is an expand-if-contains-one rule and we only provided one element it should have expanded to 'item'
            self.assertSequenceEqual([subtree.data for subtree in r.children], ('item',))

            # regardless of the amount of items: there should be only *one* child in 'start' because 'list' isn't an expand-all rule
            self.assertEqual(len(r.children), 1)

        def test_dont_expand1_lists_with_multiple_items(self):
            g = _Lark(r"""start: list
                            ?list: item+
                            item : A
                            A: "a"
                        """)
            r = g.parse("aa")

            # because 'list' is an expand-if-contains-one rule and we've provided more than one element it should *not* have expanded
            self.assertSequenceEqual([subtree.data for subtree in r.children], ('list',))

            # regardless of the amount of items: there should be only *one* child in 'start' because 'list' isn't an expand-all rule
            self.assertEqual(len(r.children), 1)

            # Sanity check: verify that 'list' contains the two 'item's we've given it
            [list] = r.children
            self.assertSequenceEqual([item.data for item in list.children], ('item', 'item'))

        def test_dont_expand1_lists_with_multiple_items_2(self):
            g = _Lark(r"""start: list
                            ?list: item+ "!"
                            item : A
                            A: "a"
                        """)
            r = g.parse("aa!")

            # because 'list' is an expand-if-contains-one rule and we've provided more than one element it should *not* have expanded
            self.assertSequenceEqual([subtree.data for subtree in r.children], ('list',))

            # regardless of the amount of items: there should be only *one* child in 'start' because 'list' isn't an expand-all rule
            self.assertEqual(len(r.children), 1)

            # Sanity check: verify that 'list' contains the two 'item's we've given it
            [list] = r.children
            self.assertSequenceEqual([item.data for item in list.children], ('item', 'item'))



        def test_empty_expand1_list(self):
            g = _Lark(r"""start: list
                            ?list: item*
                            item : A
                            A: "a"
                         """)
            r = g.parse("")

            # because 'list' is an expand-if-contains-one rule and we've provided less than one element (i.e. none) it should *not* have expanded
            self.assertSequenceEqual([subtree.data for subtree in r.children], ('list',))

            # regardless of the amount of items: there should be only *one* child in 'start' because 'list' isn't an expand-all rule
            self.assertEqual(len(r.children), 1)

            # Sanity check: verify that 'list' contains no 'item's as we've given it none
            [list] = r.children
            self.assertSequenceEqual([item.data for item in list.children], ())

        def test_empty_expand1_list_2(self):
            g = _Lark(r"""start: list
                            ?list: item* "!"?
                            item : A
                            A: "a"
                         """)
            r = g.parse("")

            # because 'list' is an expand-if-contains-one rule and we've provided less than one element (i.e. none) it should *not* have expanded
            self.assertSequenceEqual([subtree.data for subtree in r.children], ('list',))

            # regardless of the amount of items: there should be only *one* child in 'start' because 'list' isn't an expand-all rule
            self.assertEqual(len(r.children), 1)

            # Sanity check: verify that 'list' contains no 'item's as we've given it none
            [list] = r.children
            self.assertSequenceEqual([item.data for item in list.children], ())


        def test_empty_flatten_list(self):
            g = _Lark(r"""start: list
                            list: | item "," list
                            item : A
                            A: "a"
                         """)
            r = g.parse("")

            # Because 'list' is a flatten rule it's top-level element should *never* be expanded
            self.assertSequenceEqual([subtree.data for subtree in r.children], ('list',))

            # Sanity check: verify that 'list' contains no 'item's as we've given it none
            [list] = r.children
            self.assertSequenceEqual([item.data for item in list.children], ())

        @unittest.skipIf(True, "Flattening list isn't implemented (and may never be)")
        def test_single_item_flatten_list(self):
            g = _Lark(r"""start: list
                            list: | item "," list
                            item : A
                            A: "a"
                         """)
            r = g.parse("a,")

            # Because 'list' is a flatten rule it's top-level element should *never* be expanded
            self.assertSequenceEqual([subtree.data for subtree in r.children], ('list',))

            # Sanity check: verify that 'list' contains exactly the one 'item' we've given it
            [list] = r.children
            self.assertSequenceEqual([item.data for item in list.children], ('item',))

        @unittest.skipIf(True, "Flattening list isn't implemented (and may never be)")
        def test_multiple_item_flatten_list(self):
            g = _Lark(r"""start: list
                            #list: | item "," list
                            item : A
                            A: "a"
                         """)
            r = g.parse("a,a,")

            # Because 'list' is a flatten rule it's top-level element should *never* be expanded
            self.assertSequenceEqual([subtree.data for subtree in r.children], ('list',))

            # Sanity check: verify that 'list' contains exactly the two 'item's we've given it
            [list] = r.children
            self.assertSequenceEqual([item.data for item in list.children], ('item', 'item'))

        @unittest.skipIf(True, "Flattening list isn't implemented (and may never be)")
        def test_recurse_flatten(self):
            """Verify that stack depth doesn't get exceeded on recursive rules marked for flattening."""
            g = _Lark(r"""start: a | start a
                         a : A
                         A : "a" """)

            # Force PLY to write to the debug log, but prevent writing it to the terminal (uses repr() on the half-built
            # STree data structures, which uses recursion).
            g.parse("a" * (sys.getrecursionlimit() // 4))

        def test_token_collision(self):
            g = _Lark("""start: "Hello" NAME
                        NAME: /\w/+
                        %ignore " "
                    """)
            x = g.parse('Hello World')
            self.assertSequenceEqual(x.children, ['World'])
            x = g.parse('Hello HelloWorld')
            self.assertSequenceEqual(x.children, ['HelloWorld'])

        def test_token_collision2(self):
            # NOTE: This test reveals a bug in token reconstruction in Scanless Earley
            #       I probably need to re-write grammar transformation

            g = _Lark("""
                    !start: "starts"

                    %import common.LCASE_LETTER
                    """)

            x = g.parse("starts")
            self.assertSequenceEqual(x.children, ['starts'])


        # def test_string_priority(self):
        #     g = _Lark("""start: (A | /a?bb/)+
        #                  A: "a"  """)
        #     x = g.parse('abb')
        #     self.assertEqual(len(x.children), 2)

        #     # This parse raises an exception because the lexer will always try to consume
        #     # "a" first and will never match the regular expression
        #     # This behavior is subject to change!!
        #     # Thie won't happen with ambiguity handling.
        #     g = _Lark("""start: (A | /a?ab/)+
        #                  A: "a"  """)
        #     self.assertRaises(LexError, g.parse, 'aab')

        def test_undefined_rule(self):
            self.assertRaises(GrammarError, _Lark, """start: a""")

        def test_undefined_token(self):
            self.assertRaises(GrammarError, _Lark, """start: A""")

        def test_rule_collision(self):
            g = _Lark("""start: "a"+ "b"
                             | "a"+ """)
            x = g.parse('aaaa')
            x = g.parse('aaaab')

        def test_rule_collision2(self):
            g = _Lark("""start: "a"* "b"
                             | "a"+ """)
            x = g.parse('aaaa')
            x = g.parse('aaaab')
            x = g.parse('b')

        @unittest.skipIf(LEXER is None, "Regexps >1 not supported with scanless parsing")
        def test_regex_embed(self):
            g = _Lark("""start: A B C
                        A: /a/
                        B: /${A}b/
                        C: /${B}c/
                        """)
            x = g.parse('aababc')

        def test_token_embed(self):
            g = _Lark("""start: A B C
                        A: "a"
                        B: A "b"
                        C: B "c"
                        """)
            x = g.parse('aababc')

        @unittest.skipIf(LEXER in (None, 'dynamic'), "Known bug with scanless parsing")  # TODO
        def test_token_not_anon(self):
            """Tests that "a" is matched as A, rather than an anonymous token.

            That means that "a" is not filtered out, despite being an 'immediate string'.
            Whether or not this is the intuitive behavior, I'm not sure yet.

            Perhaps the right thing to do is report a collision (if such is relevant)

            -Erez
            """

            g = _Lark("""start: "a"
                        A: "a" """)
            x = g.parse('a')

            self.assertEqual(len(x.children), 1, '"a" should not be considered anonymous')
            self.assertEqual(x.children[0].type, "A")

            g = _Lark("""start: /a/
                        A: /a/ """)
            x = g.parse('a')
            self.assertEqual(len(x.children), 1, '/a/ should not be considered anonymous')
            self.assertEqual(x.children[0].type, "A")

        def test_maybe(self):
            g = _Lark("""start: ["a"] """)
            x = g.parse('a')
            x = g.parse('')

        def test_start(self):
            g = _Lark("""a: "a" a? """, start='a')
            x = g.parse('a')
            x = g.parse('aa')
            x = g.parse('aaa')

        def test_alias(self):
            g = _Lark("""start: "a" -> b """)
            x = g.parse('a')
            self.assertEqual(x.data, "b")

        def test_token_ebnf(self):
            g = _Lark("""start: A
                      A: "a"* ("b"? "c".."e")+
                      """)
            x = g.parse('abcde')
            x = g.parse('dd')

        def test_backslash(self):
            g = _Lark(r"""start: "\\" "a"
                      """)
            x = g.parse(r'\a')

            g = _Lark(r"""start: /\\\\/ /a/
                      """)
            x = g.parse(r'\a')

        def test_special_chars(self):
            g = _Lark(r"""start: "\n"
                      """)
            x = g.parse('\n')

            g = _Lark(r"""start: /\n/
                      """)
            x = g.parse('\n')


        def test_backslash2(self):
            g = _Lark(r"""start: "\"" "-"
                      """)
            x = g.parse('"-')

            g = _Lark(r"""start: /\// /-/
                      """)
            x = g.parse('/-')

        # def test_token_recurse(self):
        #     g = _Lark("""start: A
        #                  A: B
        #                  B: A
        #               """)

        def test_empty(self):
            # Fails an Earley implementation without special handling for empty rules,
            # or re-processing of already completed rules.
            g = _Lark(r"""start: _empty a "B"
                          a: _empty "A"
                          _empty:
                            """)
            x = g.parse('AB')

        def test_lexer_token_limit(self):
            "Python has a stupid limit of 100 groups in a regular expression. Test that we handle this limitation"
            tokens = {'A%d'%i:'"%d"'%i for i in range(300)}
            g = _Lark("""start: %s
                      %s""" % (' '.join(tokens), '\n'.join("%s: %s"%x for x in tokens.items())))

        def test_float_without_lexer(self):
            g = _Lark("""start: ["+"|"-"] float
                         float: digit* "." digit+ exp?
                              | digit+ exp
                         exp: ("e"|"E") ["+"|"-"] digit+
                         digit: "0"|"1"|"2"|"3"|"4"|"5"|"6"|"7"|"8"|"9"
                      """)
            g.parse("1.2")
            g.parse("-.2e9")
            g.parse("+2e-9")
            self.assertRaises(ParseError, g.parse, "+2e-9e")

        def test_keep_all_tokens(self):
            l = _Lark("""start: "a"+ """, keep_all_tokens=True)
            tree = l.parse('aaa')
            self.assertEqual(tree.children, ['a', 'a', 'a'])


        def test_token_flags(self):
            l = _Lark("""!start: "a"i+
                      """
                      )
            tree = l.parse('aA')
            self.assertEqual(tree.children, ['a', 'A'])

            l = _Lark("""!start: /a/i+
                      """
                      )
            tree = l.parse('aA')
            self.assertEqual(tree.children, ['a', 'A'])

            g = """!start: "a"i "a"
                """
            self.assertRaises(GrammarError, _Lark, g)

            g = """!start: /a/i /a/
                """
            self.assertRaises(GrammarError, _Lark, g)

            g = """start: NAME "," "a"
                   NAME: /[a-z_]/i /[a-z0-9_]/i*
                """
            l = _Lark(g)
            tree = l.parse('ab,a')
            self.assertEqual(tree.children, ['ab'])
            tree = l.parse('AB,a')
            self.assertEqual(tree.children, ['AB'])

        def test_token_flags3(self):
            l = _Lark("""!start: ABC+
                      ABC: "abc"i
                      """
                      )
            tree = l.parse('aBcAbC')
            self.assertEqual(tree.children, ['aBc', 'AbC'])

        def test_token_flags2(self):
            g = """!start: ("a"i | /a/ /b/?)+
                """
            l = _Lark(g)
            tree = l.parse('aA')
            self.assertEqual(tree.children, ['a', 'A'])


        def test_reduce_cycle(self):
            """Tests an edge-condition in the LALR parser, in which a transition state looks exactly like the end state.
            It seems that the correct solution is to explicitely distinguish finalization in the reduce() function.
            """

            l = _Lark("""
                term: A
                    | term term

                A: "a"

            """, start='term')

            tree = l.parse("aa")
            self.assertEqual(len(tree.children), 2)


        @unittest.skipIf(PARSER != 'earley', "Currently only Earley supports priority in rules")
        def test_earley_prioritization(self):
            "Tests effect of priority on result"

            grammar = """
            start: a | b
            a.1: "a"
            b.2: "a"
            """

            l = Lark(grammar, parser='earley', lexer='standard')
            res = l.parse("a")
            self.assertEqual(res.children[0].data, 'b')

            grammar = """
            start: a | b
            a.2: "a"
            b.1: "a"
            """

            l = Lark(grammar, parser='earley', lexer='standard')
            res = l.parse("a")
            self.assertEqual(res.children[0].data, 'a')



    _NAME = "Test" + PARSER.capitalize() + (LEXER or 'Scanless').capitalize()
    _TestParser.__name__ = _NAME
    globals()[_NAME] = _TestParser

# Note: You still have to import them in __main__ for the tests to run
_TO_TEST = [
        ('standard', 'earley'),
        ('dynamic', 'earley'),
        ('standard', 'lalr'),
        ('contextual', 'lalr'),
        (None, 'earley'),
]

for _LEXER, _PARSER in _TO_TEST:
    _make_parser_test(_LEXER, _PARSER)

for _LEXER in (None, 'dynamic'):
    _make_full_earley_test(_LEXER)

if __name__ == '__main__':
    unittest.main()

