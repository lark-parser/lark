from __future__ import absolute_import

import os
from unittest import TestCase, main

from lark import Lark, Token, Tree, ParseError, UnexpectedInput, UnexpectedCharacters
from lark.load_grammar import GrammarError
from lark.load_grammar import FromPackageLoader
from lark.syntax.abnf  import ABNF_GRAMMAR_ERRORS

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
        g1 =('beef   = "bEEf" / boeuf / (BE EF) \n'
             'BE     = %xBE\n'
             'EF     = %xEF\n'
             'boeuf  = "boeuf"\n')

        # the same rule in multiple lines with comments
        g2  =(' ; rules \n'
              'beef   = "bEEf" \n'
              '       / boeuf   ; beef in french \n'
              '       / (BE EF) ; bytes sequence [0xbe,0xef] \n'
              ';terminals \n'
              'BE     = %xBE\n'
              'EF     = %xEF\n'
              'boeuf  = "boeuf"\n')

        # the same rule using incremental alternatives
        g3 = ('beef   =  "bEEf"\n'
              'beef   =/ boeuf \n'
              'beef   =/ (BE EF)\n'
              'BE     = %xBE\n'
              'EF     = %xEF\n'
              'boeuf  = "boeuf"\n')

        for g in (g1, g2, g3):
            l = Lark(g, syntax='abnf', start='beef',  keep_all_tokens=True)
            self.assertEqual(l.parse(u'beef'), Tree('beef', [Token('BEEF', 'beef')]))
            self.assertEqual(l.parse(u'bEEf'), Tree('beef', [Token('BEEF', 'bEEf')]))
            self.assertEqual(l.parse(u'boeuf'), Tree('beef', [Tree('boeuf', [Token('BOEUF', 'boeuf')])]))
            self.assertEqual(l.parse(u'\xbe\xef'), Tree('beef', [Tree('BE', [Token('__ANON_0', '¾')]),
                                                                 Tree('EF', [Token('__ANON_1', 'ï')])]))

        # undefined rule
        g = g3 + 'unused-rule = BE EF beef3\n'
        self.assertRaises(GrammarError, Lark, g, syntax='abnf', start='beef')

    def test_optional(self):
        g = ('start = [ foo ] bar\n'
             'foo   = "foo"\n'
             'bar   = "bar"\n')
        l = Lark(g, syntax='abnf', keep_all_tokens=True)
        self.assertEqual(l.parse('foobar'),
                         Tree('start', [Tree('foo', ['foo']), Tree('bar', ['bar'])]))
        self.assertEqual(l.parse('bar'),
                         Tree('start', [Tree('bar', ['bar'])]))
        self.assertRaises((ParseError, UnexpectedInput), l.parse, 'foo')

    def test_empty_match_as_prose_val(self):
        # some RFCs express empty match using prose-val (e.g. empty = 0<any characters> )
        g1 = ('start = ( foo / empty ) bar\n'
              'foo   = "foo"\n'
              'bar   = "bar"\n'
              'empty = 0<alphabets>\n')
        l = Lark(g1, syntax='abnf', keep_all_tokens=False)
        self.assertEqual(l.parse('foobar'),
                         Tree('start', [Tree('foo', []), Tree('bar', [])]))
        self.assertEqual(l.parse('bar'),
                         Tree('start', [Tree('empty', []), Tree('bar', [])]))
        g2 = ('start = ( foo / anychar ) bar\n'
              'foo   = "foo"\n'
              'bar   = "bar"\n'
              'anychar = 1<alphabets>\n')
        # GrammarError is raised if prose-val is used without zero repetition
        self.assertRaises(GrammarError, Lark, g2, syntax='abnf')


    def test_repetition(self):
        g = ('start = rep-inf / rep-fixed \n'
              'rep-inf     = *"X"\n'
              'rep-fixed   = 3"F"\n')
        l = Lark(g, syntax='abnf', keep_all_tokens=False)
        self.assertEqual(l.parse('XXX'), Tree('start', [Tree('rep_inf', [])]))
        self.assertEqual(l.parse(''), Tree('start', [Tree('rep_inf', [])]))
        self.assertEqual(l.parse('FFF'), Tree('start', [Tree('rep_fixed', [])]))
        self.assertRaises((ParseError, UnexpectedInput), l.parse, u'FF')
        self.assertRaises((ParseError, UnexpectedInput), l.parse, u'FFFF')

    def test_repetition_range(self):
        g = ('start = rep-range / rep-atleast / rep-atmost\n'
             'rep-range   = 2*4%s"R"\n'
             'rep-atleast = 3*"L"\n'
             'rep-atmost  = *5"M"\n')
        l = Lark(g, syntax='abnf', keep_all_tokens=False)

        self.assertEqual(l.parse('RRR'), Tree('start', [Tree('rep_range', [])]))
        self.assertRaises((ParseError, UnexpectedInput), l.parse, u'RRRRR')
        self.assertRaises((ParseError, UnexpectedInput), l.parse, u'R')
        self.assertRaises((ParseError, UnexpectedInput), l.parse, u'RRr')  # case sensitive

        self.assertEqual(l.parse('LlL'), Tree('start', [Tree('rep_atleast', [])])) # case insensitive
        self.assertEqual(l.parse('LLLL'), Tree('start', [Tree('rep_atleast', [])]))
        self.assertRaises((ParseError, UnexpectedInput), l.parse, u'LL')

        self.assertEqual(l.parse('mmm'), Tree('start', [Tree('rep_atmost', [])]))
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
                                 Tree('start', [Tree('LALPHA', ['l']), Tree('UALPHA', ['U']),
                                                Tree('DIGIT', ['%d' % i])]))
            self.assertRaises((ParseError, UnexpectedInput), l.parse, u'lU0123456789:')


    def test_literal_concatenation(self):
        g1 = ('start       = digits12345\n'
              'digits12345 = %x31.32.33.34.35\n')
        g2 = ('start       = digits12345\n'
              'digits12345 = %b00110001.00110010.00110011.00110100.00110101\n')
        g3 = ('start       = digits12345\n'
              'digits12345 = %d49.50.51.52.53\n')
        for g in (g1, g2, g3):
            l = Lark(g, syntax='abnf', keep_all_tokens=False)
            self.assertEqual(l.parse('12345'), Tree('start', [Tree('digits12345', ['12345'])]))

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
            self.assertEqual(l.parse(unicode_char), Tree('start', [Tree('sym1', [unicode_char])]))

    def test_unicode_match_emoji(self):
        # test for 32bit unicode character
        char_vals = ('%x1F431', '%d128049', '%b00011111010000110001')
        cat_face_in_unicode = '🐱'

        template = ('start  = thecat\n'
                    'thecat = %s\n')
        grammars = [ template % i for i in char_vals]
        for g in grammars:
            l = Lark(g, syntax='abnf', keep_all_tokens=True)
            tree = l.parse(cat_face_in_unicode)
            self.assertEqual(l.parse(cat_face_in_unicode),
                             Tree('start', [Tree('thecat', [cat_face_in_unicode])]))


    def test_terminal(self):
        # '%terminal lineending' expected to turn CRLF, CR and LF into terminals (recursive search)
        g = ('start      = 1*(ALPHA/SP) lineending\n'
             'ALPHA      = %x41-5A / %x61-7A\n'
             'SP         = %x20\n'
             'lineending = CRLF\n'
             'CRLF  =  CR LF\n'
             'CR    =  %x0D\n'
             'LF    =  %x0A\n'
             '%terminal ALPHA, SP\n'
             '%terminal lineending\n')
        l = Lark(g, syntax='abnf')
        msg = 'lorem ipsum\r\n'
        tree = l.parse(msg)
        self.assertEqual(l.parse(msg),Tree('start', [c for c in 'lorem ipsum'] + ['\r\n']))


    def test_terminal_rulename_with_hyphen(self):
        # Test to make sure that hyphens in rule names is replaced with hyphens
        # so that they will not cause probrems (LALR parser can't handle it)
        g = ('start = L-ALPHA U-ALPHA 1*DIGIT \n'
             'U-ALPHA = %x41-5A \n'
             'L-ALPHA = %x61-7A \n'
             'DIGIT  = %d48-57 \n'
             '%terminal U-ALPHA, L-ALPHA\n')
        for p in ('earley', 'lalr'):
            l = Lark(g, syntax='abnf', parser=p)
            self.assertEqual(l.parse(u'aA1'),
                             Tree('start', [Token('L_ALPHA', 'a'), Token('U_ALPHA', 'A'), Tree('DIGIT', ['1'])]))

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
                         Tree('start', [Tree('startab', [Tree('expr', [Tree('A', []), Tree('B', [])])])]))

    def test_import(self):
        g1 = ('start = LALPHA UALPHA 1*DIGIT CRLF\n'
              'UALPHA = %x41-5A \n'
              'LALPHA = %x61-7A \n'
              'DIGIT = %x30-39\n'
              '%import core-rules\n')
        # GrammarError is raised since DIGIT is defined twice in both g1 and core-rules.abnf
        self.assertRaises(GrammarError, Lark, g1, syntax='abnf')

        g2 = ('start = LALPHA UALPHA 1*DIGIT CRLF\n'
              'UALPHA = %x41-5A \n'
              'LALPHA = %x61-7A \n'
              'dIGIT = %x30-39\n'
              '%import core-rules\n')
        # also GrammarError for multiple rule definition, since rule names are case insensitive
        self.assertRaises(GrammarError, Lark, g2, syntax='abnf')

        g3 = ('start = LALPHA UALPHA 1*DIGIT CRLF\n'
             'UALPHA = %x41-5A \n'
             'LALPHA = %x61-7A \n'
             'DIGIT = %x30-39\n'
             '%import core-rules ( CRLF )\n')
        # g3 is okay since only rule 'CRLF' is imported but 'DIGITS' is not
        p = Lark(g3, syntax='abnf')
        self.assertEqual(p.parse('aA1\r\n'),
                         Tree('start', [Tree('LALPHA', ['a']),
                                        Tree('UALPHA', ['A']),
                                        Tree('DIGIT',  ['1']),
                                        Tree('CRLF',  [Tree('CR', ['\r']), Tree('LF', ['\n'])])]))

    def test_rule_duplication_casefold(self):
        g1 = ('start = LALPHA UALPHA 1*DIGIT\n'
              'UALPHA = %x41-5A \n'
              'LALPHA = %x61-7A \n'
              'LaLPHA = %x61-7A \n'
              'DIGIT = %x30-39\n')
        # GrammarError is expected for multiple rule definition, since rule names are case insensitive
        self.assertRaises(GrammarError, Lark, g1, syntax='abnf')


if __name__ == '__main__':
    main()
