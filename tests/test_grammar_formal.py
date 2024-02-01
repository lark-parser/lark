from __future__ import absolute_import

import os
from unittest import TestCase, main

from lark import lark, Lark, UnexpectedToken
from lark.load_grammar import GrammarError


# Based on TestGrammar, with lots of tests that can't be run deleted.
class TestGrammarFormal(TestCase):
    def setUp(self):
        lark_path = os.path.join(os.path.dirname(lark.__file__), 'grammars/lark.lark')
        with open(lark_path, 'r') as f:
            self.lark_grammar = f.read())

    def test_errors(self):
        l = Lark(self.lark_grammar, parser="lalr")

        # This is an unrolled form of the test_grammar.py:GRAMMAR_ERRORS tests, because the lark.lark messages vary.

        # 'Incorrect type of value', 'a: 1\n'
        self.assertRaisesRegex(UnexpectedToken, 'Unexpected token Token..NUMBER., .1..', l.parse, 'a: 1\n')
        # 'Unclosed parenthesis', 'a: (\n'
        self.assertRaisesRegex(UnexpectedToken, 'Unexpected token Token.._NL.,', l.parse, 'a: (\n')
        # 'Unmatched closing parenthesis', 'a: )\n'
        self.assertRaisesRegex(UnexpectedToken, 'Unexpected token Token..RPAR.', l.parse, 'a: )\n')
        # 'Unmatched closing parenthesis', 'a: )\n'
        self.assertRaisesRegex(UnexpectedToken, 'Unexpected token Token..RPAR.,', l.parse, 'a: )\n')
        # 'Unmatched closing parenthesis', 'a: (\n'
        self.assertRaisesRegex(UnexpectedToken, 'Unexpected token Token.._NL.,', l.parse, 'a: (\n')
        # 'Expecting rule or terminal definition (missing colon)', 'a\n'
        self.assertRaisesRegex(UnexpectedToken, 'Unexpected token Token.._NL.,', l.parse, 'a\n')
        # 'Expecting rule or terminal definition (missing colon)', 'A\n'
        self.assertRaisesRegex(UnexpectedToken, 'Unexpected token Token.._NL.,', l.parse, 'A\n')
        # 'Expecting rule or terminal definition (missing colon)', 'a->\n'
        self.assertRaisesRegex(UnexpectedToken, 'Unexpected token Token..__ANON_0., .->', l.parse, 'a->\n')
        # 'Expecting rule or terminal definition (missing colon)', 'A->\n'
        self.assertRaisesRegex(UnexpectedToken, 'Unexpected token Token..__ANON_0., .->', l.parse, 'A->\n')
        # 'Expecting rule or terminal definition (missing colon)', 'a A\n'
        self.assertRaisesRegex(UnexpectedToken, 'Unexpected token Token..TOKEN., .A..', l.parse, 'a A\n')
        # 'Illegal name for rules or terminals', 'Aa:\n'
        self.assertRaisesRegex(UnexpectedToken, 'Unexpected token Token..RULE., .a..', l.parse, 'Aa:\n')
        # 'Alias expects lowercase name', 'a: -> "a"\n'
        self.assertRaisesRegex(UnexpectedToken, 'Unexpected token Token..STRING., ."a"..', l.parse, 'a: -> "a"\n')
        # 'Unexpected colon', 'a::\n'
        self.assertRaisesRegex(UnexpectedToken, 'Unexpected token Token..COLON.,', l.parse, 'a::\n')
        # 'Unexpected colon', 'a: b:\n'
        self.assertRaisesRegex(UnexpectedToken, 'Unexpected token Token..COLON.,', l.parse, 'a: b:\n')
        # 'Unexpected colon', 'a: B:\n'
        self.assertRaisesRegex(UnexpectedToken, 'Unexpected token Token..COLON.,', l.parse, 'a: B:\n')
        # 'Unexpected colon', 'a: "a":\n'
        self.assertRaisesRegex(UnexpectedToken, 'Unexpected token Token..COLON.,', l.parse, 'a: "a":\n')
        # 'Misplaced operator', 'a: b??'
        self.assertRaisesRegex(UnexpectedToken, 'Unexpected token Token..OP., .\?..', l.parse, 'a: b??')
        # 'Misplaced operator', 'a: b(?)'
        self.assertRaisesRegex(UnexpectedToken, 'Unexpected token Token..OP., .\?..', l.parse, 'a: b(?)')
        # 'Misplaced operator', 'a:+\n'
        self.assertRaisesRegex(UnexpectedToken, 'Unexpected token Token..OP., .\+..', l.parse, 'a:+\n')
        # 'Misplaced operator', 'a:?\n'
        self.assertRaisesRegex(UnexpectedToken, 'Unexpected token Token..OP., .\?..', l.parse, 'a:?\n')
        # 'Misplaced operator', 'a:*\n'
        self.assertRaisesRegex(UnexpectedToken, 'Unexpected token Token..OP., .\*..', l.parse, 'a:*\n')
        # 'Misplaced operator', 'a:|*\n'
        self.assertRaisesRegex(UnexpectedToken, 'Unexpected token Token..OP., .\*..', l.parse, 'a:|*\n')
        # 'Expecting option ("|") or a new rule or terminal definition', 'a:a\n()\n'
        self.assertRaisesRegex(UnexpectedToken, 'Unexpected token Token..LPAR.,', l.parse, 'a:a\n()\n')
        # 'Terminal names cannot contain dots', 'A.B\n'
        self.assertRaisesRegex(UnexpectedToken, 'Unexpected token Token..TOKEN., .B..', l.parse, 'A.B\n')
        # 'Expecting rule or terminal definition', '"a"\n'
        self.assertRaisesRegex(UnexpectedToken, 'Unexpected token Token..STRING., ."a"..', l.parse, '"a"\n')
        # '%import expects a name', '%import "a"\n'
        self.assertRaisesRegex(UnexpectedToken, 'Unexpected token Token..STRING., ."a"..', l.parse, '%import "a"\n')
        # '%ignore expects a value', '%ignore %import\n'
        self.assertRaisesRegex(UnexpectedToken, 'Unexpected token Token..__ANON_2., .%import..', l.parse, '%ignore %import\n')

    def test_alias_in_terminal(self):
        l = Lark(self.lark_grammar, parser="lalr")
        g = """start: TERM
            TERM: "a" -> alias
            """
        # self.assertRaisesRegex( GrammarError, "Aliasing not allowed in terminals", Lark, g)
        self.assertRaisesRegex( UnexpectedToken, "Unexpected token Token.'__ANON_0', '->'.", l.parse, g)

    def test_inline_with_expand_single(self):
        l = Lark(self.lark_grammar, parser="lalr")
        grammar = r"""
        start: _a
        !?_a: "A"
        """
        # self.assertRaisesRegex(GrammarError, "Inlined rules (_rule) cannot use the ?rule modifier.", l.parse, grammar)
        self.assertRaisesRegex(UnexpectedToken, "Unexpected token Token.'OP', '?'.", l.parse, grammar)


if __name__ == '__main__':
    main()
