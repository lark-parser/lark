from __future__ import absolute_import

import os
from unittest import TestCase, main

from lark import lark, Lark, UnexpectedToken
from lark.load_grammar import GrammarError


# Based on TestGrammar, with lots of tests that can't be run elided.
class TestGrammarFormal(TestCase):
    def setUp(self):
        lark_path = os.path.join(os.path.dirname(lark.__file__), 'grammars/lark.lark')
        # lark_path = os.path.join(os.path.dirname(lark.__file__), 'grammars/lark.lark-ORIG')
        with open(lark_path, 'r') as f:
            self.lark_grammar = "\n".join(f.readlines())

    def test_errors(self):
        # raise NotImplementedError("Doesn't work yet.")
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

    # def test_empty_literal(self):
        # raise NotImplementedError("Breaks tests/test_parser.py:_TestParser:test_backslash2().")

    # def test_ignore_name(self):
        # raise NotImplementedError("Can't parse using parsed grammar.")

    # def test_override_rule_1(self):
        # raise NotImplementedError("Can't parse using parsed grammar.")

    # def test_override_rule_2(self):
        # raise NotImplementedError("Can't test semantics of grammar, only syntax.")

    # def test_override_rule_3(self):
        # raise NotImplementedError("Can't test semantics of grammar, only syntax.")

    # def test_override_terminal(self):
        # raise NotImplementedError("Can't parse using parsed grammar.")

    # def test_extend_rule_1(self):
        # raise NotImplementedError("Can't parse using parsed grammar.")

    # def test_extend_rule_2(self):
        # raise NotImplementedError("Can't test semantics of grammar, only syntax.")

    # def test_extend_term(self):
        # raise NotImplementedError("Can't parse using parsed grammar.")

    # def test_extend_twice(self):
        # raise NotImplementedError("Can't parse using parsed grammar.")

    # def test_undefined_ignore(self):
        # raise NotImplementedError("Can't parse using parsed grammar.")

    def test_alias_in_terminal(self):
        l = Lark(self.lark_grammar, parser="lalr")
        g = """start: TERM
            TERM: "a" -> alias
            """
        # self.assertRaisesRegex( GrammarError, "Aliasing not allowed in terminals", Lark, g)
        self.assertRaisesRegex( UnexpectedToken, "Unexpected token Token.'__ANON_0', '->'.", l.parse, g)

    # def test_undefined_rule(self):
        # raise NotImplementedError("Can't test semantics of grammar, only syntax.")

    # def test_undefined_term(self):
        # raise NotImplementedError("Can't test semantics of grammar, only syntax.")

    # def test_token_multiline_only_works_with_x_flag(self):
        # raise NotImplementedError("Can't test regex flags in Lark grammar.")

    # def test_import_custom_sources(self):
        # raise NotImplementedError("Can't parse using parsed grammar.")

    # def test_import_custom_sources2(self):
        # raise NotImplementedError("Can't parse using parsed grammar.")

    # def test_import_custom_sources3(self):
        # raise NotImplementedError("Can't parse using parsed grammar.")

    # def test_my_find_grammar_errors(self):
        # raise NotImplementedError("Can't parse using parsed grammar.")

    # def test_ranged_repeat_terms(self):
        # raise NotImplementedError("Can't parse using parsed grammar.")

    # def test_ranged_repeat_large(self):
        # raise NotImplementedError("Can't parse using parsed grammar.")

    # def test_large_terminal(self):
        # raise NotImplementedError("Can't parse using parsed grammar.")

    # def test_list_grammar_imports(self):
        # raise NotImplementedError("Can't test semantics of grammar, only syntax.")

    def test_inline_with_expand_single(self):
        l = Lark(self.lark_grammar, parser="lalr")
        grammar = r"""
        start: _a
        !?_a: "A"
        """
        # self.assertRaisesRegex(GrammarError, "Inlined rules (_rule) cannot use the ?rule modifier.", l.parse, grammar)
        # TODO Is this really catching the right problem?
        self.assertRaisesRegex(UnexpectedToken, "Unexpected token Token.'OP', '?'.", l.parse, grammar)


    # def test_line_breaks(self):
        # raise NotImplementedError("Can't parse using parsed grammar.")


if __name__ == '__main__':
    main()
