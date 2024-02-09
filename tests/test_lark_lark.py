from __future__ import absolute_import

from unittest import TestCase, main

from lark import lark, Lark, UnexpectedToken
from lark.load_grammar import GrammarError
from lark.lark_validator_visitor import LarkValidatorVisitor


# Test that certain previous differences between load_grammar.py and
# grammars/lark.lark have been resolved.
class TestLarkLark(TestCase):
    def setUp(self):
        self.lark_parser = Lark.open_from_package("lark", "grammars/lark.lark", parser="lalr")

    def test_01_no_alias_in_terminal_lg(self):
        g = """start: TERM
            TERM: "a" -> alias
            """
        self.assertRaisesRegex( GrammarError, "Aliasing not allowed in terminals", Lark, g)

    def test_01_no_alias_in_terminal_ll(self):
        # lark.lark allows aliases in terminals, and rejects them if you run the LarkValidatorVisitor.
        g = """start: TERM
            TERM: "a" -> alias
            """
        self.lark_parser.parse(g)

    def test_02_no_rule_aliases_below_top_level_lg(self):
        g = """start: rule
            rule: ("a" -> alias
                 | "b")
            """
        self.assertRaisesRegex( GrammarError, "Rule 'alias' used but not defined", Lark, g)

    def test_02_no_rule_aliases_below_top_level_ll(self):
        # lark.lark allows aliases below top-level, and rejects them if you run the LarkValidatorVisitor.
        g = """start: rule
            rule: ("a" -> alias
                 | "b")
            """
        self.lark_parser.parse(g)

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
        self.assertRaisesRegex( AssertionError, "Tree.'template_usage', .NonTerminal.'separated'.", Lark, g)

    def test_06_no_term_templates_ll(self):
        # lark.lark allows templates in terminals, and rejects them if you run the LarkValidatorVisitor.
        g = """start: TERM
        separated{x, sep}: x (sep x)*
        TERM: separated{"A", " "}
        """
        self.lark_parser.parse(g)

    def test_07_term_no_call_rule_lg(self):
        g = """start: TERM
        TERM: rule
        rule: "a"
        """
        self.assertRaisesRegex( GrammarError, "Rules aren't allowed inside terminals", Lark, g)

    def test_07_term_no_call_rule_ll(self):
        # lark.lark allows rules in terminals, and rejects them if you run the LarkValidatorVisitor.
        g = """start: TERM
        TERM: rule
        rule: "a"
        """
        self.lark_parser.parse(g)

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

    def test_lark_validator_alias_top_level_ok(self):
        g = """
            start: rule1
            rule1: rule2 -> alias2
        """
        t = self.lark_parser.parse(g)
        LarkValidatorVisitor.validate(t)

    def test_lark_validator_alias_inner_bad(self):
        g = """
            start: rule1
            rule1: rule2
                 | (rule3 -> alias3 | rule4)
            rule2: "a"
            rule3: "b"
            rule4: "c"
        """

        t = self.lark_parser.parse(g)
        self.assertRaisesRegex( Exception, "Deep aliasing not allowed", LarkValidatorVisitor.validate, t)

    def test_lark_validator_import_multi_token_bad(self):
        g = """
            %ignore A B
            start: rule1
            rule1: "c"
            A: "a"
            B: "b"
        """
        t = self.lark_parser.parse(g)
        self.assertRaisesRegex(GrammarError, "Bad %ignore - must have a Terminal or other value", LarkValidatorVisitor.validate, t)

    def test_lark_validator_terminal_alias_bad(self):
        g = """
            start: rule1
            rule1: TOKEN2
            TOKEN2: "a" -> alias2
        """
        t = self.lark_parser.parse(g)
        self.assertRaisesRegex(GrammarError, "Aliasing not allowed in terminals", LarkValidatorVisitor.validate, t)

    def test_lark_validator_terminal_rule_bad(self):
        g = """start: TERM
        TERM: rule
        rule: "a"
        """
        t = self.lark_parser.parse(g)
        self.assertRaisesRegex(GrammarError, "Rules aren't allowed inside terminals", LarkValidatorVisitor.validate, t)

    def test_lark_validator_terminal_template_bad(self):
        g = """start: TERM
        separated{x, sep}: x (sep x)*
        TERM: separated{"A", " "}
        """
        t = self.lark_parser.parse(g)
        self.assertRaisesRegex(GrammarError, "Templates not allowed in terminals", LarkValidatorVisitor.validate, t)


if __name__ == '__main__':
    main()
