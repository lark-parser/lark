from __future__ import absolute_import

import os
from unittest import TestCase, main

from lark import Lark, Token, Tree, ParseError, UnexpectedInput, UnexpectedCharacters
from lark.load_grammar import GrammarError
from lark.load_grammar import FromPackageLoader
from lark.load_grammar_abnf import ABNF_GRAMMAR_ERRORS

class TestABNFGrammar(TestCase):
    def setUp(self):
        pass

    def test_charval_case_insensitive(self):
        p = Lark('rulename = %i"aBc" / "xyz"\n', syntax='abnf', start='rulename')
        abcs = ["abc", "Abc", "aBc", "abC", "ABc", "aBC", "AbC", "ABC"]
        xyzs = ["xyz", "Xyz", "XYZ" ]
        for i in abcs + xyzs:
            self.assertEqual(p.parse(i), Tree('rulename', []))

    def test_charval_case_sensitive(self):
        p = Lark('rulename = %s"aBc" / %s"xyZ"\n', syntax='abnf', start='rulename')
        for i in ('aBc', 'xyZ'):
            self.assertEqual(p.parse(i), Tree('rulename', []))

        for i in ('abc', 'xYy'):
            self.assertRaises(UnexpectedCharacters, p.parse, i)

    def test_inline_numval(self):
        # test for anonymous rules generated for inline num-val (%x22)
        g = ('cat = %x40 "cat" %x40\n')
        l = Lark(g, syntax='abnf', start='cat',  keep_all_tokens=True)
        self.assertEqual(l.parse('@cat@'),
                         Tree('cat', [Token('__ANON_0', '@'), Token('CAT', 'cat'), Token('__ANON_0', '@')]))

    def test_basic_abnf(self):
        # test for alternatives, concatenation, and grouping
        g1 =('beef   = %s"bEEf" / beef2 / (BE EF) \n'
             'BE     = %xBE\n'
             'EF     = %xEF\n'
             'beef2  = %s"beef"\n')

        # the same rule in multiple lines with comments
        g2 =(' ; rules \n'
             'beef   = %s"bEEf" \n'
             '       / beef2   ; word "beef" in lowercase \n'
             '       / (BE EF) ; bytes sequence [0xbe,0xef] \n'
             ';terminals \n'
             'BE     = %xBE\n'
             'EF     = %xEF\n'
             'beef2  = %s"beef"\n')

        # the same rule using incremental alternatives
        g3 = ('beef   =  %s"bEEf"\n'
             'beef   =/ beef2 \n'
             'beef   =/ (BE EF)\n'
             'BE     = %xBE\n'
             'EF     = %xEF\n'
             'beef2  = %s"beef"\n')

        for g in (g1, g2, g3):
            l = Lark(g, syntax='abnf', start='beef',  keep_all_tokens=True)
            self.assertEqual(l.parse(u'beef'), Tree('beef', [Token('beef2', 'beef')]))
            self.assertEqual(l.parse(u'bEEf'), Tree('beef', [Token('BEEF', 'bEEf')]))
            self.assertEqual(l.parse(u'\xbe\xef'), Tree('beef', [Token('BE', '\xbe'), Token('EF', '\xef')]))

        # undefined rule
        g = g3 + 'unused-rule = BE EF beef3\n'
        self.assertRaises(GrammarError, Lark, g, syntax='abnf', start='beef')

    def test_optional(self):
        g = ('start = [ foo ] bar\n'
             'foo   = "foo"\n'
             'bar   = "bar"\n')
        l = Lark(g, syntax='abnf', keep_all_tokens=False)
        self.assertEqual(l.parse('foobar'),
                         Tree('start', [Token('foo', 'foo'), Token('bar', 'bar')]))
        self.assertEqual(l.parse('bar'),
                         Tree('start', [Token('bar', 'bar')]))
        self.assertRaises((ParseError, UnexpectedInput), l.parse, 'foo')


    def test_repetition(self):
        g = ('start = rep-inf / rep-fixed \n'
              'rep-inf     = *"X"\n'
              'rep-fixed   = 3"F"\n')
        l = Lark(g, syntax='abnf', keep_all_tokens=False)
        self.assertEqual(l.parse('XXX'), Tree('start', [Tree('rep-inf', [])]))
        self.assertEqual(l.parse(''), Tree('start', [Tree('rep-inf', [])]))
        self.assertEqual(l.parse('FFF'), Tree('start', [Tree('rep-fixed', [])]))
        self.assertRaises((ParseError, UnexpectedInput), l.parse, u'FF')
        self.assertRaises((ParseError, UnexpectedInput), l.parse, u'FFFF')

    def test_repetition_range(self):
        g = ('start = rep-range / rep-atleast / rep-atmost\n'
             'rep-range   = 2*4%s"R"\n'
             'rep-atleast = 3*"L"\n'
             'rep-atmost  = *5"M"\n')
        l = Lark(g, syntax='abnf', keep_all_tokens=False)

        self.assertEqual(l.parse('RRR'), Tree('start', [Tree('rep-range', [])]))
        self.assertRaises((ParseError, UnexpectedInput), l.parse, u'RRRRR')
        self.assertRaises((ParseError, UnexpectedInput), l.parse, u'R')
        self.assertRaises((ParseError, UnexpectedInput), l.parse, u'RRr')  # case sensitive

        self.assertEqual(l.parse('LlL'), Tree('start', [Tree('rep-atleast', [])])) # case insensitive
        self.assertEqual(l.parse('LLLL'), Tree('start', [Tree('rep-atleast', [])]))
        self.assertRaises((ParseError, UnexpectedInput), l.parse, u'LL')

        self.assertEqual(l.parse('mmm'), Tree('start', [Tree('rep-atmost', [])]))
        self.assertRaises((ParseError, UnexpectedInput), l.parse, u'mmmmmm')

    def test_zero_repetition(self):
        g1 = ('start = ("cat" / "dog" / empty) "food" \n'
             'empty = 0<animals>\n')
        l = Lark(g1, syntax='abnf', keep_all_tokens=True)
        self.assertEqual(l.parse("catfood"), Tree('start', [Token('CAT', 'cat'), Token('FOOD', 'food')]))
        self.assertEqual(l.parse("dogfood"), Tree('start', [Token('DOG', 'dog'), Token('FOOD', 'food')]))
        self.assertEqual(l.parse("food"), Tree('start', [Tree('empty', []), Token('FOOD', 'food')]))
        self.assertRaises((UnexpectedInput), l.parse, u"petfood")

    def test_literal_range(self):

        g1 = ('start = LALPHA UALPHA 1*DIGIT\n'
              'UALPHA = %x41-5A \n'
              'LALPHA = %x61-7A \n'
              'DIGIT = %x30-39\n')
        g2 = ('start = LALPHA UALPHA 1*DIGIT\n'
              'UALPHA = %x41-5A \n'
              'LALPHA = %x61-7A \n'
              'DIGIT  = %d48-57 \n')
        g3 = ('start = LALPHA UALPHA 1*DIGIT\n'
              'UALPHA = %x41-5A \n'
              'LALPHA = %x61-7A \n'
              'DIGIT  = %b00110000-00111001 \n')
        for g in (g1, g2, g3):
            l = Lark(g, syntax='abnf')
            for i in (0,1,2,3,4,5,6,7,8,9):
                self.assertEqual(l.parse('lU%d' % i),
                                 Tree('start', [Token('LALPHA', 'l'), Token('UALPHA', 'U'),
                                                Token('DIGIT', '%d' % i)]))
            self.assertRaises((ParseError, UnexpectedInput), l.parse, u'lU0123456789:')


    def test_literal_concatenation(self):
        g1 = ('start       = digits12345\n'
              'digits12345 = %x31.32.33.34.35\n')
        g2 = ('start       = digits12345\n'
              'digits12345 = %b00110001.00110010.00110011.00110100.00110101\n')
        g3 = ('start       = digits12345\n'
              'digits12345 = %x49.50.51.52.53\n')
        #for g in (g1, g2, g3):
        for g in (g1,):
            l = Lark(g, syntax='abnf', keep_all_tokens=False)
            self.assertEqual(l.parse('12345'), Tree('start', [Token('digits12345', '12345')]))

    def test_operator_precedence(self):
        # concatenation has higher precedence than alternation
        g = ('start = "a" / "b" "c"\n')
        l = Lark(g, syntax='abnf', keep_all_tokens=True)
        self.assertEqual(l.parse('bc'), Tree('start', [Token('B', 'b'), Token('C', 'c')]))
        self.assertEqual(l.parse('a'),  Tree('start', [Token('A', 'a')]))

        self.assertRaises((ParseError, UnexpectedInput), l.parse, 'ac')

        # grouping
        g = ('start = ("a" / "b") "c"\n')
        l = Lark(g, syntax='abnf', keep_all_tokens=True)
        self.assertEqual(l.parse('bc'), Tree('start', [Token('B', 'b'), Token('C', 'c')]))
        self.assertEqual(l.parse('ac'), Tree('start', [Token('A', 'a'), Token('C', 'c')]))

    def test_unicode_match(self):
        # test for 16bit unicode character
        char_vals = ('%x2227', '%d8743', '%b0010001000100111')
        unicode_char = '∧'

        template = ('start = sym1\n'
                    'sym1  = %s\n')
        grammars = [ template % i for i in char_vals]
        for g in grammars:
            l = Lark(g, syntax='abnf', keep_all_tokens=True)
            self.assertEqual(l.parse(unicode_char), Tree('start', [Token('sym1', unicode_char)]))

    def test_unicode_match_emoji(self):
        # test for 32bit unicode character
        char_vals = ('%x1F431', '%d128049', '%b00011111010000110001')
        cat_face_in_unicode = '🐱'

        template = ('start  = thecat\n'
                    'thecat = %s\n')
        grammars = [ template % i for i in char_vals]
        for g in grammars:
            l = Lark(g, syntax='abnf', keep_all_tokens=True)
            self.assertEqual(l.parse(cat_face_in_unicode),
                             Tree('start', [Token('thecat', cat_face_in_unicode)]))

    def test_terminal_rulename_with_hyphen(self):
        # test to make sure that rule names may contain hyphen.
        g = ('start = L-ALPHA U-ALPHA 1*DIGIT \n'
             'U-ALPHA = %x41-5A \n'
             'L-ALPHA = %x61-7A \n'
             'DIGIT  = %d48-57 \n')
        l = Lark(g, syntax='abnf')
        self.assertEqual(l.parse(u'aA1'), Tree('start', [Token('L-ALPHA', 'a'), Token('U-ALPHA', 'A'), Token('DIGIT', '1')]))

    def test_errors(self):
        for msg, examples in ABNF_GRAMMAR_ERRORS:
            for example in examples:
                try:
                    p = Lark(example, syntax='abnf')
                except GrammarError as e:
                    assert msg in str(e)
                else:
                    assert False, "example did not raise an error"

    def test_import_from_custom_sources(self):
        custom_loader = FromPackageLoader('tests', ('grammars', ))
        g1 = ('start = startab \n'
              '%import ab\n')
        p = Lark(g1, syntax='abnf', start='start', import_paths=[custom_loader])
        self.assertEqual(p.parse('ab'),
                         Tree('start', [Tree('startab', [Tree('expr', [Token('A', 'a'), Token('B', 'b')])])]))

    def test_import(self):
        g1 = ('start = LALPHA UALPHA 1*DIGIT CRLF\n'
              'UALPHA = %x41-5A \n'
              'LALPHA = %x61-7A \n'
              'DIGIT = %x30-39\n'
              '%import core-rules\n')
        # grammar error is expected since DIGIT is defined twice in both g1 and core-rules.abnf
        self.assertRaises(GrammarError, Lark, g1, syntax='abnf')

        g2 = ('start = LALPHA UALPHA 1*DIGIT CRLF\n'
             'UALPHA = %x41-5A \n'
             'LALPHA = %x61-7A \n'
             'DIGIT = %x30-39\n'
             '%import core-rules ( CRLF )\n')
        # g2 is okay since only rule 'CRLF' is imported but 'DIGITS' is not
        p = Lark(g2, syntax='abnf')
        self.assertEqual(p.parse('aA1\r\n'),
                         Tree('start', [Token('LALPHA', 'a'), Token('UALPHA', 'A'),
                                        Token('DIGIT', '1'),
                                        Tree('CRLF', [Token('CR', '\r'), Token('LF', '\n')])]))


if __name__ == '__main__':
    main()
