from __future__ import absolute_import

from unittest import TestCase, main

from lark import lark, Lark, UnexpectedToken
from lark.load_grammar import GrammarError


# Based on TestGrammar, with lots of tests that can't be run deleted.
class TestGrammarFormal(TestCase):
    def setUp(self):
        self.lark_parser = Lark.open_from_package("lark", "grammars/lark.lark", parser="lalr")

    def test_errors(self):
        # This is an unrolled form of the test_grammar.py:GRAMMAR_ERRORS tests, because the lark.lark messages vary.

        # 'Incorrect type of value', 'a: 1\n'
        self.assertRaisesRegex(UnexpectedToken, 'Unexpected token Token..NUMBER., .1..', self.lark_parser.parse, 'a: 1\n')
        # 'Unclosed parenthesis', 'a: (\n'
        self.assertRaisesRegex(UnexpectedToken, 'Unexpected token Token.._NL.,', self.lark_parser.parse, 'a: (\n')
        # 'Unmatched closing parenthesis', 'a: )\n'
        self.assertRaisesRegex(UnexpectedToken, 'Unexpected token Token..RPAR.', self.lark_parser.parse, 'a: )\n')
        # 'Unmatched closing parenthesis', 'a: )\n'
        self.assertRaisesRegex(UnexpectedToken, 'Unexpected token Token..RPAR.,', self.lark_parser.parse, 'a: )\n')
        # 'Unmatched closing parenthesis', 'a: (\n'
        self.assertRaisesRegex(UnexpectedToken, 'Unexpected token Token.._NL.,', self.lark_parser.parse, 'a: (\n')
        # 'Expecting rule or terminal definition (missing colon)', 'a\n'
        self.assertRaisesRegex(UnexpectedToken, 'Unexpected token Token.._NL.,', self.lark_parser.parse, 'a\n')
        # 'Expecting rule or terminal definition (missing colon)', 'A\n'
        self.assertRaisesRegex(UnexpectedToken, 'Unexpected token Token.._NL.,', self.lark_parser.parse, 'A\n')
        # 'Expecting rule or terminal definition (missing colon)', 'a->\n'
        self.assertRaisesRegex(UnexpectedToken, 'Unexpected token Token..__ANON_0., .->', self.lark_parser.parse, 'a->\n')
        # 'Expecting rule or terminal definition (missing colon)', 'A->\n'
        self.assertRaisesRegex(UnexpectedToken, 'Unexpected token Token..__ANON_0., .->', self.lark_parser.parse, 'A->\n')
        # 'Expecting rule or terminal definition (missing colon)', 'a A\n'
        self.assertRaisesRegex(UnexpectedToken, 'Unexpected token Token..TOKEN., .A..', self.lark_parser.parse, 'a A\n')
        # 'Illegal name for rules or terminals', 'Aa:\n'
        self.assertRaisesRegex(UnexpectedToken, 'Unexpected token Token..RULE., .a..', self.lark_parser.parse, 'Aa:\n')
        # 'Alias expects lowercase name', 'a: -> "a"\n'
        self.assertRaisesRegex(UnexpectedToken, 'Unexpected token Token..STRING., ."a"..', self.lark_parser.parse, 'a: -> "a"\n')
        # 'Unexpected colon', 'a::\n'
        self.assertRaisesRegex(UnexpectedToken, 'Unexpected token Token..COLON.,', self.lark_parser.parse, 'a::\n')
        # 'Unexpected colon', 'a: b:\n'
        self.assertRaisesRegex(UnexpectedToken, 'Unexpected token Token..COLON.,', self.lark_parser.parse, 'a: b:\n')
        # 'Unexpected colon', 'a: B:\n'
        self.assertRaisesRegex(UnexpectedToken, 'Unexpected token Token..COLON.,', self.lark_parser.parse, 'a: B:\n')
        # 'Unexpected colon', 'a: "a":\n'
        self.assertRaisesRegex(UnexpectedToken, 'Unexpected token Token..COLON.,', self.lark_parser.parse, 'a: "a":\n')
        # 'Misplaced operator', 'a: b??'
        self.assertRaisesRegex(UnexpectedToken, 'Unexpected token Token..OP., .\?..', self.lark_parser.parse, 'a: b??')
        # 'Misplaced operator', 'a: b(?)'
        self.assertRaisesRegex(UnexpectedToken, 'Unexpected token Token..OP., .\?..', self.lark_parser.parse, 'a: b(?)')
        # 'Misplaced operator', 'a:+\n'
        self.assertRaisesRegex(UnexpectedToken, 'Unexpected token Token..OP., .\+..', self.lark_parser.parse, 'a:+\n')
        # 'Misplaced operator', 'a:?\n'
        self.assertRaisesRegex(UnexpectedToken, 'Unexpected token Token..OP., .\?..', self.lark_parser.parse, 'a:?\n')
        # 'Misplaced operator', 'a:*\n'
        self.assertRaisesRegex(UnexpectedToken, 'Unexpected token Token..OP., .\*..', self.lark_parser.parse, 'a:*\n')
        # 'Misplaced operator', 'a:|*\n'
        self.assertRaisesRegex(UnexpectedToken, 'Unexpected token Token..OP., .\*..', self.lark_parser.parse, 'a:|*\n')
        # 'Expecting option ("|") or a new rule or terminal definition', 'a:a\n()\n'
        self.assertRaisesRegex(UnexpectedToken, 'Unexpected token Token..LPAR.,', self.lark_parser.parse, 'a:a\n()\n')
        # 'Terminal names cannot contain dots', 'A.B\n'
        self.assertRaisesRegex(UnexpectedToken, 'Unexpected token Token..TOKEN., .B..', self.lark_parser.parse, 'A.B\n')
        # 'Expecting rule or terminal definition', '"a"\n'
        self.assertRaisesRegex(UnexpectedToken, 'Unexpected token Token..STRING., ."a"..', self.lark_parser.parse, '"a"\n')
        # '%import expects a name', '%import "a"\n'
        self.assertRaisesRegex(UnexpectedToken, 'Unexpected token Token..STRING., ."a"..', self.lark_parser.parse, '%import "a"\n')
        # '%ignore expects a value', '%ignore %import\n'
        self.assertRaisesRegex(UnexpectedToken, 'Unexpected token Token..__ANON_2., .%import..', self.lark_parser.parse, '%ignore %import\n')

    def test_alias_in_terminal(self):
        g = """start: TERM
            TERM: "a" -> alias
            """
        self.assertRaisesRegex( UnexpectedToken, "Unexpected token Token.'__ANON_0', '->'.", self.lark_parser.parse, g)

    def test_inline_with_expand_single(self):
        grammar = r"""
        start: _a
        !?_a: "A"
        """
        self.assertRaisesRegex(UnexpectedToken, "Unexpected token Token.'OP', '?'.", self.lark_parser.parse, grammar)


if __name__ == '__main__':
    main()
