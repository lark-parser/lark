from __future__ import absolute_import

import os
from unittest import TestCase, main

from lark import lark, Lark, UnexpectedToken
from lark.load_grammar import GrammarError


# Test that certain previous differences between load_grammar.py and 
# grammars/lark.lark have been resolved.
class TestLarkLark(TestCase):
    def setUp(self):
        lark_path = os.path.join(os.path.dirname(lark.__file__), 'grammars/lark.lark')
        self.lark_parser = Lark.open(lark_path, parser="lalr")

    def test_01_no_alias_in_terminal_lg(self):
        g = """start: TERM
            TERM: "a" -> alias
            """
        self.assertRaisesRegex( GrammarError, "Aliasing not allowed in terminals", Lark, g)

    def test_01_no_alias_in_terminal_ll(self):
        g = """start: TERM
            TERM: "a" -> alias
            """
        self.assertRaisesRegex( UnexpectedToken, "Unexpected token Token.'__ANON_0', '->'.", self.lark_parser.parse, g)

    def test_02_no_rule_aliases_below_top_level_lg(self):
        g = """start: rule
            rule: ("a" -> alias
                 | "b")
            """
        self.assertRaisesRegex( GrammarError, "Rule 'alias' used but not defined", Lark, g)

    def test_02_no_rule_aliases_below_top_level_ll(self):
        g = """start: rule
            rule: ("a" -> alias
                 | "b")
            """
        self.assertRaisesRegex( UnexpectedToken, "Unexpected token Token.'__ANON_0', '->'.", self.lark_parser.parse, g)

    def test_03_ignore_single_token_lg(self):
        g = """start: TERM
        %ignore "a" "b" /c/
        TERM: "d"
        """
        # This SHOULD raise some sort of error, but silently discards the extra tokens instead.
        # self.assertRaises( UnexpectedToken, Lark, g)
        Lark(g)

    def test_03_ignore_single_token_ll(self):
        g = """start: TERM
        %ignore "a" "b" /c/
        TERM: "d"
        """
        self.assertRaisesRegex( UnexpectedToken, "Unexpected token Token.'STRING', '.b.'.", self.lark_parser.parse, g)

    def test_04_extend_rule_lg(self):
        g = """
            %import .grammars.ab (startab, A, B, expr)

            %extend expr: B A
        """
        Lark(g, start='startab', source_path=__file__)

    def test_04_extend_rule_ll(self):
        g = """
            %import .grammars.ab (startab, A, B, expr)

            %extend expr: B A
        """
        self.lark_parser.parse(g)

    def test_05_extend_term_lg(self):
        g = """
            %import .grammars.ab (startab, A, B, expr)

            %extend A: "c"
        """
        Lark(g, start='startab', source_path=__file__)

    def test_05_extend_term_ll(self):
        g = """
            %import .grammars.ab (startab, A, B, expr)

            %extend A: "c"
        """
        self.lark_parser.parse(g)

    def test_06_no_term_templates_lg(self):
        g = """start: TERM
        separated{x, sep}: x (sep x)*
        TERM: separated{"A", " "}
        """
        self.assertRaises( AssertionError, Lark, g)

    def test_06_no_term_templates_ll(self):
        g = """start: TERM
        separated{x, sep}: x (sep x)*
        TERM: separated{"A", " "}
        """
        self.assertRaisesRegex( UnexpectedToken, "Unexpected token Token.'RULE', 'separated'.", self.lark_parser.parse, g)

    def test_07_term_no_call_rule_lg(self):
        g = """start: TERM
        TERM: rule
        rule: "a"
        """
        self.assertRaisesRegex( GrammarError, "Rules aren't allowed inside terminals", Lark, g)

    def test_07_term_no_call_rule_ll(self):
        g = """start: TERM
        TERM: rule
        rule: "a"
        """
        self.assertRaisesRegex( UnexpectedToken, "Unexpected token Token.'RULE', 'rule'.", self.lark_parser.parse, g)

    def test_08_override_term_lg(self):
        g = """
            %import .grammars.ab (startab, A, B, expr)

            %override A: "c"
        """
        Lark(g, start='startab', source_path=__file__)

    def test_08_override_term_ll(self):
        g = """
            %import .grammars.ab (startab, A, B, expr)

            %override A: "c"
        """
        self.lark_parser.parse(g)

    def test_09_no_rule_modifiers_in_references_lg(self):
        g = """start: rule1
            rule1: !?rule2
            rule2: "a"
        """
        self.assertRaisesRegex(GrammarError, "Expecting a value, at line 2 column 20", Lark, g)

    def test_09_no_rule_modifiers_in_references_ll(self):
        g = """start: rule1
            rule1: !rule2
            rule2: "a"
        """
        self.assertRaisesRegex( UnexpectedToken, "Unexpected token Token.'RULE_MODIFIERS', '!'.", self.lark_parser.parse, g)

    def test_10_rule_modifier_query_bang_lg(self):
        g = """start: rule1
            rule1: rule2
            ?!rule2: "a"
        """
        Lark(g)

    def test_10_rule_modifier_query_bang_ll(self):
        g = """start: rule1
            rule1: rule2
            ?!rule2: "a"
        """
        self.lark_parser.parse(g)

if __name__ == '__main__':
    main()
