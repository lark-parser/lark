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
                    NAME: /\w+/ """)
        l2 = g.parse('(a,b,c,*x)')
        assert l == l2, '%s != %s' % (l.pretty(), l2.pretty())

class TestEarley(unittest.TestCase):
    pass

def _make_parser_test(PARSER):
    def _Lark(grammar, **kwargs):
        return Lark(grammar, parser=PARSER, **kwargs)
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

        def test_unicode2(self):
            g = _Lark(r"""start: UNIA UNIB UNIA UNIC
                        UNIA: /\xa3/
                        UNIB: "a\u0101b\ "
                        UNIC: /a?\u0101c\n/
                        """)
            g.parse(u'\xa3a\u0101b\\ \u00a3\u0101c\n')


        def test_recurse_expansion(self):
            """Verify that stack depth doesn't get exceeded on recursive rules marked for expansion."""
            g = _Lark(r"""start: a | start a
                         a : "a" """)

            # Force PLY to write to the debug log, but prevent writing it to the terminal (uses repr() on the half-built
            # STree data structures, which uses recursion).
            g.parse("a" * (sys.getrecursionlimit() // 4))

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
                        NAME: /\w+/
                        WS.ignore: /\s+/
                    """)
            x = g.parse('Hello World')
            self.assertSequenceEqual(x.children, ['World'])
            x = g.parse('Hello HelloWorld')
            self.assertSequenceEqual(x.children, ['HelloWorld'])

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

        def test_regex_embed(self):
            g = _Lark("""start: A B C
                        A: /a/
                        B: /${A}b/
                        C: /${B}c/
                        """)
            x = g.parse('aababc')

        def test_token_not_anon(self):
            """Tests that "a" is matched as A, rather than an anonymous token.

            That means that "a" is not filtered out, despite being an 'immediate string'.
            Whether or not this is the intuitive behavior, I'm not sure yet.

            -Erez
            """

            g = _Lark("""start: "a"
                        A: "a" """)
            x = g.parse('a')
            self.assertEqual(len(x.children), 1, '"a" should not be considered anonymous')
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

        def test_lexer_token_limit(self):
            "Python has a stupid limit of 100 groups in a regular expression. Test that we handle this limitation"
            tokens = {'A%d'%i:'"%d"'%i for i in range(300)}
            g = _Lark("""start: %s
                      %s""" % (' '.join(tokens), '\n'.join("%s: %s"%x for x in tokens.items())))


    _NAME = "Test" + PARSER.capitalize()
    _TestParser.__name__ = _NAME
    globals()[_NAME] = _TestParser

for PARSER in ['lalr', 'earley']:
    _make_parser_test(PARSER)



if __name__ == '__main__':
    unittest.main()

