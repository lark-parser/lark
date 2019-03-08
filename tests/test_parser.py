# -*- coding: utf-8 -*-
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
from lark.exceptions import GrammarError, ParseError, UnexpectedToken, UnexpectedInput, UnexpectedCharacters
from lark.tree import Tree
from lark.visitors import Transformer

__path__ = os.path.dirname(__file__)
def _read(n, *args):
    with open(os.path.join(__path__, n), *args) as f:
        return f.read()

class TestParsers(unittest.TestCase):
    def test_same_ast(self):
        "Tests that Earley and LALR parsers produce equal trees"
        g = Lark(r"""start: "(" name_list ("," "*" NAME)? ")"
                    name_list: NAME | name_list "," NAME
                    NAME: /\w+/ """, parser='lalr')
        l = g.parse('(a,b,c,*x)')

        g = Lark(r"""start: "(" name_list ("," "*" NAME)? ")"
                    name_list: NAME | name_list "," NAME
                    NAME: /\w/+ """)
        l2 = g.parse('(a,b,c,*x)')
        assert l == l2, '%s != %s' % (l.pretty(), l2.pretty())

    def test_infinite_recurse(self):
        g = """start: a
               a: a | "a"
            """

        self.assertRaises(GrammarError, Lark, g, parser='lalr')

        # TODO: should it? shouldn't it?
        # l = Lark(g, parser='earley', lexer='dynamic')
        # self.assertRaises(ParseError, l.parse, 'a')

    def test_propagate_positions(self):
        g = Lark("""start: a
                    a: "a"
                 """, propagate_positions=True)

        r = g.parse('a')
        self.assertEqual( r.children[0].meta.line, 1 )

    def test_expand1(self):

        g = Lark("""start: a
                    ?a: b
                    b: "x"
                 """)

        r = g.parse('x')
        self.assertEqual( r.children[0].data, "b" )

        g = Lark("""start: a
                    ?a: b -> c
                    b: "x"
                 """)

        r = g.parse('x')
        self.assertEqual( r.children[0].data, "c" )

        g = Lark("""start: a
                    ?a: B -> c
                    B: "x"
                 """)
        self.assertEqual( r.children[0].data, "c" )


        g = Lark("""start: a
                    ?a: b b -> c
                    b: "x"
                 """)
        r = g.parse('xx')
        self.assertEqual( r.children[0].data, "c" )

    def test_embedded_transformer(self):
        class T(Transformer):
            def a(self, children):
                return "<a>"
            def b(self, children):
                return "<b>"
            def c(self, children):
                return "<c>"

        # Test regular
        g = Lark("""start: a
                    a : "x"
                 """, parser='lalr')
        r = T().transform(g.parse("x"))
        self.assertEqual( r.children, ["<a>"] )


        g = Lark("""start: a
                    a : "x"
                 """, parser='lalr', transformer=T())
        r = g.parse("x")
        self.assertEqual( r.children, ["<a>"] )


        # Test Expand1
        g = Lark("""start: a
                    ?a : b
                    b : "x"
                 """, parser='lalr')
        r = T().transform(g.parse("x"))
        self.assertEqual( r.children, ["<b>"] )


        g = Lark("""start: a
                    ?a : b
                    b : "x"
                 """, parser='lalr', transformer=T())
        r = g.parse("x")
        self.assertEqual( r.children, ["<b>"] )

        # Test Expand1 -> Alias
        g = Lark("""start: a
                    ?a : b b -> c
                    b : "x"
                 """, parser='lalr')
        r = T().transform(g.parse("xx"))
        self.assertEqual( r.children, ["<c>"] )


        g = Lark("""start: a
                    ?a : b b -> c
                    b : "x"
                 """, parser='lalr', transformer=T())
        r = g.parse("xx")
        self.assertEqual( r.children, ["<c>"] )


    def test_alias(self):
        Lark("""start: ["a"] "b" ["c"] "e" ["f"] ["g"] ["h"] "x" -> d """)



def _make_full_earley_test(LEXER):
    def _Lark(grammar, **kwargs):
        return Lark(grammar, lexer=LEXER, parser='earley', propagate_positions=True, **kwargs)
    class _TestFullEarley(unittest.TestCase):
        def test_anon(self):
            # Fails an Earley implementation without special handling for empty rules,
            # or re-processing of already completed rules.
            g = Lark(r"""start: B
                         B: ("ab"|/[^b]/)+
                      """, lexer=LEXER)

            self.assertEqual( g.parse('abc').children[0], 'abc')

        def test_earley(self):
            g = Lark("""start: A "b" c
                        A: "a"+
                        c: "abc"
                        """, parser="earley", lexer=LEXER)
            x = g.parse('aaaababc')

        def test_earley2(self):
            grammar = """
            start: statement+

            statement: "r"
                     | "c" /[a-z]/+

            %ignore " "
            """

            program = """c b r"""

            l = Lark(grammar, parser='earley', lexer=LEXER)
            l.parse(program)


        @unittest.skipIf(LEXER=='dynamic', "Only relevant for the dynamic_complete parser")
        def test_earley3(self):
            """Tests prioritization and disambiguation for pseudo-terminals (there should be only one result)

            By default, `+` should immitate regexp greedy-matching
            """
            grammar = """
            start: A A
            A: "a"+
            """

            l = Lark(grammar, parser='earley', lexer=LEXER)
            res = l.parse("aaa")
            self.assertEqual(set(res.children), {'aa', 'a'})
            # XXX TODO fix Earley to maintain correct order
            # i.e. terminals it imitate greedy search for terminals, but lazy search for rules
            # self.assertEqual(res.children, ['aa', 'a'])

        def test_earley4(self):
            grammar = """
            start: A A?
            A: "a"+
            """

            l = Lark(grammar, parser='earley', lexer=LEXER)
            res = l.parse("aaa")
            assert set(res.children) == {'aa', 'a'} or res.children == ['aaa']
            # XXX TODO fix Earley to maintain correct order
            # i.e. terminals it imitate greedy search for terminals, but lazy search for rules
            # self.assertEqual(res.children, ['aaa'])

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

        @unittest.skipIf(LEXER=='standard', "Requires dynamic lexer")
        def test_earley_explicit_ambiguity(self):
            # This was a sneaky bug!

            grammar = """
            start: a b | ab
            a: "a"
            b: "b"
            ab: "ab"
            """

            parser = Lark(grammar, parser='earley', lexer=LEXER, ambiguity='explicit')
            ambig_tree = parser.parse('ab')
            self.assertEqual( ambig_tree.data, '_ambig')
            self.assertEqual( len(ambig_tree.children), 2)

        @unittest.skipIf(LEXER=='standard', "Requires dynamic lexer")
        def test_ambiguity1(self):
            grammar = """
            start: cd+ "e"

            !cd: "c"
               | "d"
               | "cd"

            """
            l = Lark(grammar, parser='earley', ambiguity='explicit', lexer=LEXER)
            ambig_tree = l.parse('cde')

            assert ambig_tree.data == '_ambig', ambig_tree
            assert len(ambig_tree.children) == 2

        @unittest.skipIf(LEXER=='standard', "Requires dynamic lexer")
        def test_ambiguity2(self):
            grammar = """
            ANY:  /[a-zA-Z0-9 ]+/
            a.2: "A" b+
            b.2: "B"
            c:   ANY

            start: (a|c)*
            """
            l = Lark(grammar, parser='earley', lexer=LEXER)
            res = l.parse('ABX')
            expected = Tree('start', [
                    Tree('a', [
                        Tree('b', [])
                    ]),
                    Tree('c', [
                        'X'
                    ])
                ])
            self.assertEqual(res, expected)

        def test_fruitflies_ambig(self):
            grammar = """
                start: noun verb noun        -> simple
                        | noun verb "like" noun -> comparative

                noun: adj? NOUN
                verb: VERB
                adj: ADJ

                NOUN: "flies" | "bananas" | "fruit"
                VERB: "like" | "flies"
                ADJ: "fruit"

                %import common.WS
                %ignore WS
            """
            parser = Lark(grammar, ambiguity='explicit', lexer=LEXER)
            tree = parser.parse('fruit flies like bananas')

            expected = Tree('_ambig', [
                    Tree('comparative', [
                        Tree('noun', ['fruit']),
                        Tree('verb', ['flies']),
                        Tree('noun', ['bananas'])
                    ]),
                    Tree('simple', [
                        Tree('noun', [Tree('adj', ['fruit']), 'flies']),
                        Tree('verb', ['like']),
                        Tree('noun', ['bananas'])
                    ])
                ])

            # self.assertEqual(tree, expected)
            self.assertEqual(tree.data, expected.data)
            self.assertEqual(set(tree.children), set(expected.children))


        @unittest.skipIf(LEXER!='dynamic_complete', "Only relevant for the dynamic_complete parser")
        def test_explicit_ambiguity2(self):
            grammar = r"""
            start: NAME+
            NAME: /\w+/
            %ignore " "
            """
            text = """cat"""

            parser = _Lark(grammar, start='start', ambiguity='explicit')
            tree = parser.parse(text)
            self.assertEqual(tree.data, '_ambig')

            combinations = {tuple(str(s) for s in t.children) for t in tree.children}
            self.assertEqual(combinations, {
                ('cat',),
                ('ca', 't'),
                ('c', 'at'),
                ('c', 'a' ,'t')
            })

        def test_term_ambig_resolve(self):
            grammar = r"""
            !start: NAME+
            NAME: /\w+/
            %ignore " "
            """
            text = """foo bar"""

            parser = Lark(grammar)
            tree = parser.parse(text)
            self.assertEqual(tree.children, ['foo', 'bar'])






        # @unittest.skipIf(LEXER=='dynamic', "Not implemented in Dynamic Earley yet")  # TODO
        # def test_not_all_derivations(self):
        #     grammar = """
        #     start: cd+ "e"

        #     !cd: "c"
        #        | "d"
        #        | "cd"

        #     """
        #     l = Lark(grammar, parser='earley', ambiguity='explicit', lexer=LEXER, earley__all_derivations=False)
        #     x = l.parse('cde')
        #     assert x.data != '_ambig', x
        #     assert len(x.children) == 1

    _NAME = "TestFullEarley" + LEXER.capitalize()
    _TestFullEarley.__name__ = _NAME
    globals()[_NAME] = _TestFullEarley


def _make_parser_test(LEXER, PARSER):
    def _Lark(grammar, **kwargs):
        return Lark(grammar, lexer=LEXER, parser=PARSER, propagate_positions=True, **kwargs)
    def _Lark_open(gfilename, **kwargs):
        return Lark.open(gfilename, lexer=LEXER, parser=PARSER, propagate_positions=True, **kwargs)
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

        def test_unicode3(self):
            g = _Lark(r"""start: UNIA UNIB UNIA UNIC
                        UNIA: /\xa3/
                        UNIB: "\u0101"
                        UNIC: /\u0203/ /\n/
                        """)
            g.parse(u'\xa3\u0101\u00a3\u0203\n')

        def test_hex_escape(self):
            g = _Lark(r"""start: A B C
                          A: "\x01"
                          B: /\x02/
                          C: "\xABCD"
                          """)
            g.parse('\x01\x02\xABCD')

        def test_unicode_literal_range_escape(self):
            g = _Lark(r"""start: A+
                          A: "\u0061".."\u0063"
                          """)
            g.parse('abc')

        def test_hex_literal_range_escape(self):
            g = _Lark(r"""start: A+
                          A: "\x01".."\x03"
                          """)
            g.parse('\x01\x02\x03')

        @unittest.skipIf(PARSER == 'cyk', "Takes forever")
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



        @unittest.skipIf(PARSER == 'cyk', "No empty rules")
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

        @unittest.skipIf(PARSER == 'cyk', "No empty rules")
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


        @unittest.skipIf(PARSER == 'cyk', "No empty rules")
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
            g = _Lark(r"""start: "Hello" NAME
                        NAME: /\w/+
                        %ignore " "
                    """)
            x = g.parse('Hello World')
            self.assertSequenceEqual(x.children, ['World'])
            x = g.parse('Hello HelloWorld')
            self.assertSequenceEqual(x.children, ['HelloWorld'])

        def test_token_collision_WS(self):
            g = _Lark(r"""start: "Hello" NAME
                        NAME: /\w/+
                        %import common.WS
                        %ignore WS
                    """)
            x = g.parse('Hello World')
            self.assertSequenceEqual(x.children, ['World'])
            x = g.parse('Hello HelloWorld')
            self.assertSequenceEqual(x.children, ['HelloWorld'])


        def test_token_collision2(self):
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

        def test_token_not_anon(self):
            """Tests that "a" is matched as an anonymous token, and not A.
            """

            g = _Lark("""start: "a"
                        A: "a" """)
            x = g.parse('a')
            self.assertEqual(len(x.children), 0, '"a" should be considered anonymous')

            g = _Lark("""start: "a" A
                        A: "a" """)
            x = g.parse('aa')
            self.assertEqual(len(x.children), 1, 'only "a" should be considered anonymous')
            self.assertEqual(x.children[0].type, "A")

            g = _Lark("""start: /a/
                        A: /a/ """)
            x = g.parse('a')
            self.assertEqual(len(x.children), 1)
            self.assertEqual(x.children[0].type, "A", "A isn't associated with /a/")

        @unittest.skipIf(PARSER == 'cyk', "No empty rules")
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

            g = _Lark(r"""start: /\\/ /a/
                      """)
            x = g.parse(r'\a')


        def test_backslash2(self):
            g = _Lark(r"""start: "\"" "-"
                      """)
            x = g.parse('"-')

            g = _Lark(r"""start: /\// /-/
                      """)
            x = g.parse('/-')



        def test_special_chars(self):
            g = _Lark(r"""start: "\n"
                      """)
            x = g.parse('\n')

            g = _Lark(r"""start: /\n/
                      """)
            x = g.parse('\n')


        # def test_token_recurse(self):
        #     g = _Lark("""start: A
        #                  A: B
        #                  B: A
        #               """)

        @unittest.skipIf(PARSER == 'cyk', "No empty rules")
        def test_empty(self):
            # Fails an Earley implementation without special handling for empty rules,
            # or re-processing of already completed rules.
            g = _Lark(r"""start: _empty a "B"
                          a: _empty "A"
                          _empty:
                            """)
            x = g.parse('AB')

        def test_regex_quote(self):
            g = r"""
            start: SINGLE_QUOTED_STRING | DOUBLE_QUOTED_STRING
            SINGLE_QUOTED_STRING  : /'[^']*'/
            DOUBLE_QUOTED_STRING  : /"[^"]*"/
            """

            g = _Lark(g)
            self.assertEqual( g.parse('"hello"').children, ['"hello"'])
            self.assertEqual( g.parse("'hello'").children, ["'hello'"])


        def test_lexer_token_limit(self):
            "Python has a stupid limit of 100 groups in a regular expression. Test that we handle this limitation"
            tokens = {'A%d'%i:'"%d"'%i for i in range(300)}
            g = _Lark("""start: %s
                      %s""" % (' '.join(tokens), '\n'.join("%s: %s"%x for x in tokens.items())))

        def test_float_without_lexer(self):
            expected_error = UnexpectedCharacters if LEXER.startswith('dynamic') else UnexpectedToken
            if PARSER == 'cyk':
                expected_error = ParseError

            g = _Lark("""start: ["+"|"-"] float
                         float: digit* "." digit+ exp?
                              | digit+ exp
                         exp: ("e"|"E") ["+"|"-"] digit+
                         digit: "0"|"1"|"2"|"3"|"4"|"5"|"6"|"7"|"8"|"9"
                      """)
            g.parse("1.2")
            g.parse("-.2e9")
            g.parse("+2e-9")
            self.assertRaises( expected_error, g.parse, "+2e-9e")

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

            # g = """!start: "a"i "a"
            #     """
            # self.assertRaises(GrammarError, _Lark, g)

            # g = """!start: /a/i /a/
            #     """
            # self.assertRaises(GrammarError, _Lark, g)

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


        @unittest.skipIf(PARSER == 'cyk', "No empty rules")
        def test_twice_empty(self):
            g = """!start: [["A"]]
                """
            l = _Lark(g)
            tree = l.parse('A')
            self.assertEqual(tree.children, ['A'])

            tree = l.parse('')
            self.assertEqual(tree.children, [])

        def test_undefined_ignore(self):
            g = """!start: "A"

                %ignore B
                """
            self.assertRaises( GrammarError, _Lark, g)

        def test_alias_in_terminal(self):
            g = """start: TERM
                TERM: "a" -> alias
                """
            self.assertRaises( GrammarError, _Lark, g)

        def test_line_and_column(self):
            g = r"""!start: "A" bc "D"
                !bc: "B\nC"
                """
            l = _Lark(g)
            a, bc, d = l.parse("AB\nCD").children
            self.assertEqual(a.line, 1)
            self.assertEqual(a.column, 1)

            bc ,= bc.children
            self.assertEqual(bc.line, 1)
            self.assertEqual(bc.column, 2)

            self.assertEqual(d.line, 2)
            self.assertEqual(d.column, 2)

            if LEXER != 'dynamic':
                self.assertEqual(a.end_line, 1)
                self.assertEqual(a.end_column, 2)
                self.assertEqual(bc.end_line, 2)
                self.assertEqual(bc.end_column, 2)
                self.assertEqual(d.end_line, 2)
                self.assertEqual(d.end_column, 3)



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


        @unittest.skipIf(LEXER != 'standard', "Only standard lexers care about token priority")
        def test_lexer_prioritization(self):
            "Tests effect of priority on result"

            grammar = """
            start: A B | AB
            A.2: "a"
            B: "b"
            AB: "ab"
            """
            l = _Lark(grammar)
            res = l.parse("ab")

            self.assertEqual(res.children, ['a', 'b'])
            self.assertNotEqual(res.children, ['ab'])

            grammar = """
            start: A B | AB
            A: "a"
            B: "b"
            AB.3: "ab"
            """
            l = _Lark(grammar)
            res = l.parse("ab")

            self.assertNotEqual(res.children, ['a', 'b'])
            self.assertEqual(res.children, ['ab'])



        def test_import(self):
            grammar = """
            start: NUMBER WORD

            %import common.NUMBER
            %import common.WORD
            %import common.WS
            %ignore WS

            """
            l = _Lark(grammar)
            x = l.parse('12 elephants')
            self.assertEqual(x.children, ['12', 'elephants'])


        def test_import_rename(self):
            grammar = """
            start: N W

            %import common.NUMBER -> N
            %import common.WORD -> W
            %import common.WS
            %ignore WS

            """
            l = _Lark(grammar)
            x = l.parse('12 elephants')
            self.assertEqual(x.children, ['12', 'elephants'])


        def test_relative_import(self):
            l = _Lark_open('test_relative_import.lark', rel_to=__file__)
            x = l.parse('12 lions')
            self.assertEqual(x.children, ['12', 'lions'])


        def test_relative_import_rename(self):
            l = _Lark_open('test_relative_import_rename.lark', rel_to=__file__)
            x = l.parse('12 lions')
            self.assertEqual(x.children, ['12', 'lions'])


        def test_relative_rule_import(self):
            l = _Lark_open('test_relative_rule_import.lark', rel_to=__file__)
            x = l.parse('xaabby')
            self.assertEqual(x.children, [
                'x',
                Tree('expr', ['a', Tree('expr', ['a', 'b']), 'b']),
                'y'])


        def test_relative_rule_import_drop_ignore(self):
            # %ignore rules are dropped on import
            l = _Lark_open('test_relative_rule_import_drop_ignore.lark',
                           rel_to=__file__)
            self.assertRaises((ParseError, UnexpectedInput),
                              l.parse, 'xa abby')


        def test_relative_rule_import_subrule(self):
            l = _Lark_open('test_relative_rule_import_subrule.lark',
                           rel_to=__file__)
            x = l.parse('xaabby')
            self.assertEqual(x.children, [
                'x',
                Tree('startab', [
                    Tree('grammars__ab__expr', [
                        'a', Tree('grammars__ab__expr', ['a', 'b']), 'b',
                    ]),
                ]),
                'y'])


        def test_relative_rule_import_subrule_no_conflict(self):
            l = _Lark_open(
                'test_relative_rule_import_subrule_no_conflict.lark',
                rel_to=__file__)
            x = l.parse('xaby')
            self.assertEqual(x.children, [Tree('expr', [
                'x',
                Tree('startab', [
                    Tree('grammars__ab__expr', ['a', 'b']),
                ]),
                'y'])])
            self.assertRaises((ParseError, UnexpectedInput),
                              l.parse, 'xaxabyby')


        def test_relative_rule_import_rename(self):
            l = _Lark_open('test_relative_rule_import_rename.lark',
                           rel_to=__file__)
            x = l.parse('xaabby')
            self.assertEqual(x.children, [
                'x',
                Tree('ab', ['a', Tree('ab', ['a', 'b']), 'b']),
                'y'])


        def test_multi_import(self):
            grammar = """
            start: NUMBER WORD

            %import common (NUMBER, WORD, WS)
            %ignore WS

            """
            l = _Lark(grammar)
            x = l.parse('12 toucans')
            self.assertEqual(x.children, ['12', 'toucans'])


        def test_relative_multi_import(self):
            l = _Lark_open("test_relative_multi_import.lark", rel_to=__file__)
            x = l.parse('12 capybaras')
            self.assertEqual(x.children, ['12', 'capybaras'])

        def test_import_errors(self):
            grammar = """
            start: NUMBER WORD

            %import .grammars.bad_test.NUMBER
            """
            self.assertRaises(IOError, _Lark, grammar)

            grammar = """
            start: NUMBER WORD

            %import bad_test.NUMBER
            """
            self.assertRaises(IOError, _Lark, grammar)

        @unittest.skipIf(PARSER != 'earley', "Currently only Earley supports priority in rules")
        def test_earley_prioritization(self):
            "Tests effect of priority on result"

            grammar = """
            start: a | b
            a.1: "a"
            b.2: "a"
            """

            # l = Lark(grammar, parser='earley', lexer='standard')
            l = _Lark(grammar)
            res = l.parse("a")
            self.assertEqual(res.children[0].data, 'b')

            grammar = """
            start: a | b
            a.2: "a"
            b.1: "a"
            """

            l = _Lark(grammar)
            # l = Lark(grammar, parser='earley', lexer='standard')
            res = l.parse("a")
            self.assertEqual(res.children[0].data, 'a')



        @unittest.skipIf(PARSER != 'earley', "Currently only Earley supports priority in rules")
        def test_earley_prioritization_sum(self):
            "Tests effect of priority on result"

            grammar = """
            start: ab_ b_ a_ | indirection
            indirection: a_ bb_ a_
            a_: "a"
            b_: "b"
            ab_: "ab"
            bb_.1: "bb"
            """

            l = Lark(grammar, priority="invert")
            res = l.parse('abba')
            self.assertEqual(''.join(child.data for child in res.children), 'ab_b_a_')

            grammar = """
            start: ab_ b_ a_ | indirection
            indirection: a_ bb_ a_
            a_: "a"
            b_: "b"
            ab_.1: "ab"
            bb_: "bb"
            """

            l = Lark(grammar, priority="invert")
            res = l.parse('abba')
            self.assertEqual(''.join(child.data for child in res.children), 'indirection')

            grammar = """
            start: ab_ b_ a_ | indirection
            indirection: a_ bb_ a_
            a_.2: "a"
            b_.1: "b"
            ab_.3: "ab"
            bb_.3: "bb"
            """

            l = Lark(grammar, priority="invert")
            res = l.parse('abba')
            self.assertEqual(''.join(child.data for child in res.children), 'ab_b_a_')

            grammar = """
            start: ab_ b_ a_ | indirection
            indirection: a_ bb_ a_
            a_.1: "a"
            b_.1: "b"
            ab_.4: "ab"
            bb_.3: "bb"
            """

            l = Lark(grammar, priority="invert")
            res = l.parse('abba')
            self.assertEqual(''.join(child.data for child in res.children), 'indirection')


        def test_utf8(self):
            g = u"""start: a
                   a: "±a"
                """
            l = _Lark(g)
            self.assertEqual(l.parse(u'±a'), Tree('start', [Tree('a', [])]))

            g = u"""start: A
                   A: "±a"
                """
            l = _Lark(g)
            self.assertEqual(l.parse(u'±a'), Tree('start', [u'\xb1a']))



        @unittest.skipIf(PARSER == 'cyk', "No empty rules")
        def test_ignore(self):
            grammar = r"""
            COMMENT: /(!|(\/\/))[^\n]*/
            %ignore COMMENT
            %import common.WS -> _WS
            %import common.INT
            start: "INT"i _WS+ INT _WS*
            """

            parser = _Lark(grammar)

            tree = parser.parse("int 1 ! This is a comment\n")
            self.assertEqual(tree.children, ['1'])

            tree = parser.parse("int 1 ! This is a comment")    # A trailing ignore token can be tricky!
            self.assertEqual(tree.children, ['1'])

            parser = _Lark(r"""
                start : "a"*
                %ignore "b"
            """)
            tree = parser.parse("bb")
            self.assertEqual(tree.children, [])


        def test_regex_escaping(self):
            g = _Lark("start: /[ab]/")
            g.parse('a')
            g.parse('b')

            self.assertRaises( UnexpectedInput, g.parse, 'c')

            _Lark(r'start: /\w/').parse('a')

            g = _Lark(r'start: /\\w/')
            self.assertRaises( UnexpectedInput, g.parse, 'a')
            g.parse(r'\w')

            _Lark(r'start: /\[/').parse('[')

            _Lark(r'start: /\//').parse('/')

            _Lark(r'start: /\\/').parse('\\')

            _Lark(r'start: /\[ab]/').parse('[ab]')

            _Lark(r'start: /\\[ab]/').parse('\\a')

            _Lark(r'start: /\t/').parse('\t')

            _Lark(r'start: /\\t/').parse('\\t')

            _Lark(r'start: /\\\t/').parse('\\\t')

            _Lark(r'start: "\t"').parse('\t')

            _Lark(r'start: "\\t"').parse('\\t')

            _Lark(r'start: "\\\t"').parse('\\\t')


        def test_ranged_repeat_rules(self):
            g = u"""!start: "A"~3
                """
            l = _Lark(g)
            self.assertEqual(l.parse(u'AAA'), Tree('start', ["A", "A", "A"]))
            self.assertRaises(ParseError, l.parse, u'AA')
            self.assertRaises((ParseError, UnexpectedInput), l.parse, u'AAAA')


            g = u"""!start: "A"~0..2
                """
            if PARSER != 'cyk': # XXX CYK currently doesn't support empty grammars
                l = _Lark(g)
                self.assertEqual(l.parse(u''), Tree('start', []))
                self.assertEqual(l.parse(u'A'), Tree('start', ['A']))
                self.assertEqual(l.parse(u'AA'), Tree('start', ['A', 'A']))
                self.assertRaises((UnexpectedToken, UnexpectedInput), l.parse, u'AAA')

            g = u"""!start: "A"~3..2
                """
            self.assertRaises(GrammarError, _Lark, g)

            g = u"""!start: "A"~2..3 "B"~2
                """
            l = _Lark(g)
            self.assertEqual(l.parse(u'AABB'), Tree('start', ['A', 'A', 'B', 'B']))
            self.assertEqual(l.parse(u'AAABB'), Tree('start', ['A', 'A', 'A', 'B', 'B']))
            self.assertRaises(ParseError, l.parse, u'AAAB')
            self.assertRaises((ParseError, UnexpectedInput), l.parse, u'AAABBB')
            self.assertRaises((ParseError, UnexpectedInput), l.parse, u'ABB')
            self.assertRaises((ParseError, UnexpectedInput), l.parse, u'AAAABB')


        def test_ranged_repeat_terms(self):
            g = u"""!start: AAA
                    AAA: "A"~3
                """
            l = _Lark(g)
            self.assertEqual(l.parse(u'AAA'), Tree('start', ["AAA"]))
            self.assertRaises((ParseError, UnexpectedInput), l.parse, u'AA')
            self.assertRaises((ParseError, UnexpectedInput), l.parse, u'AAAA')

            g = u"""!start: AABB CC
                    AABB: "A"~0..2 "B"~2
                    CC: "C"~1..2
                """
            l = _Lark(g)
            self.assertEqual(l.parse(u'AABBCC'), Tree('start', ['AABB', 'CC']))
            self.assertEqual(l.parse(u'BBC'), Tree('start', ['BB', 'C']))
            self.assertEqual(l.parse(u'ABBCC'), Tree('start', ['ABB', 'CC']))
            self.assertRaises((ParseError, UnexpectedInput), l.parse, u'AAAB')
            self.assertRaises((ParseError, UnexpectedInput), l.parse, u'AAABBB')
            self.assertRaises((ParseError, UnexpectedInput), l.parse, u'ABB')
            self.assertRaises((ParseError, UnexpectedInput), l.parse, u'AAAABB')

        @unittest.skipIf(PARSER=='earley', "Priority not handled correctly right now")  # TODO XXX
        def test_priority_vs_embedded(self):
            g = """
            A.2: "a"
            WORD: ("a".."z")+

            start: (A | WORD)+
            """
            l = _Lark(g)
            t = l.parse('abc')
            self.assertEqual(t.children, ['a', 'bc'])
            self.assertEqual(t.children[0].type, 'A')

        def test_line_counting(self):
            p = _Lark("start: /[^x]+/")

            text = 'hello\nworld'
            t = p.parse(text)
            tok = t.children[0]
            self.assertEqual(tok, text)
            self.assertEqual(tok.line, 1)
            self.assertEqual(tok.column, 1)
            if _LEXER != 'dynamic':
                self.assertEqual(tok.end_line, 2)
                self.assertEqual(tok.end_column, 6)

        @unittest.skipIf(PARSER=='cyk', "Empty rules")
        def test_empty_end(self):
            p = _Lark("""
                start: b c d
                b: "B"
                c: | "C"
                d: | "D"
            """)
            res = p.parse('B')
            self.assertEqual(len(res.children), 3)

        @unittest.skipIf(PARSER=='cyk', "Empty rules")
        def test_maybe_placeholders(self):
            # Anonymous tokens shouldn't count
            p = _Lark("""start: ["a"] ["b"] ["c"] """, maybe_placeholders=True)
            self.assertEqual(p.parse("").children, [])

            # All invisible constructs shouldn't count
            p = _Lark("""start: [A] ["b"] [_c] ["e" "f" _c]
                        A: "a"
                        _c: "c" """, maybe_placeholders=True)
            self.assertEqual(p.parse("").children, [None])
            self.assertEqual(p.parse("c").children, [None])
            self.assertEqual(p.parse("aefc").children, ['a'])

            # ? shouldn't apply
            p = _Lark("""!start: ["a"] "b"? ["c"] """, maybe_placeholders=True)
            self.assertEqual(p.parse("").children, [None, None])
            self.assertEqual(p.parse("b").children, [None, 'b', None])

            p = _Lark("""!start: ["a"] ["b"] ["c"] """, maybe_placeholders=True)
            self.assertEqual(p.parse("").children, [None, None, None])
            self.assertEqual(p.parse("a").children, ['a', None, None])
            self.assertEqual(p.parse("b").children, [None, 'b', None])
            self.assertEqual(p.parse("c").children, [None, None, 'c'])
            self.assertEqual(p.parse("ab").children, ['a', 'b', None])
            self.assertEqual(p.parse("ac").children, ['a', None, 'c'])
            self.assertEqual(p.parse("bc").children, [None, 'b', 'c'])
            self.assertEqual(p.parse("abc").children, ['a', 'b', 'c'])

            p = _Lark("""!start: (["a"] "b" ["c"])+ """, maybe_placeholders=True)
            self.assertEqual(p.parse("b").children, [None, 'b', None])
            self.assertEqual(p.parse("bb").children, [None, 'b', None, None, 'b', None])
            self.assertEqual(p.parse("abbc").children, ['a', 'b', None, None, 'b', 'c'])
            self.assertEqual(p.parse("babbcabcb").children,
                [None, 'b', None,
                 'a', 'b', None,
                 None, 'b', 'c',
                 'a', 'b', 'c',
                 None, 'b', None])

            p = _Lark("""!start: ["a"] ["c"] "b"+ ["a"] ["d"] """, maybe_placeholders=True)
            self.assertEqual(p.parse("bb").children, [None, None, 'b', 'b', None, None])
            self.assertEqual(p.parse("bd").children, [None, None, 'b', None, 'd'])
            self.assertEqual(p.parse("abba").children, ['a', None, 'b', 'b', 'a', None])
            self.assertEqual(p.parse("cbbbb").children, [None, 'c', 'b', 'b', 'b', 'b', None, None])


        def test_escaped_string(self):
            "Tests common.ESCAPED_STRING"
            grammar = r"""
            start: ESCAPED_STRING+

            %import common (WS_INLINE, ESCAPED_STRING)
            %ignore WS_INLINE
            """

            parser = _Lark(grammar)
            parser.parse(r'"\\" "b" "c"')

            parser.parse(r'"That" "And a \"b"')


    _NAME = "Test" + PARSER.capitalize() + LEXER.capitalize()
    _TestParser.__name__ = _NAME
    globals()[_NAME] = _TestParser

# Note: You still have to import them in __main__ for the tests to run
_TO_TEST = [
        ('standard', 'earley'),
        ('standard', 'cyk'),
        ('dynamic', 'earley'),
        ('dynamic_complete', 'earley'),
        ('standard', 'lalr'),
        ('contextual', 'lalr'),
        # (None, 'earley'),
]

for _LEXER, _PARSER in _TO_TEST:
    _make_parser_test(_LEXER, _PARSER)

for _LEXER in ('dynamic', 'dynamic_complete'):
    _make_full_earley_test(_LEXER)

if __name__ == '__main__':
    unittest.main()
