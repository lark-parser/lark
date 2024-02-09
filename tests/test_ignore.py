from __future__ import absolute_import

import os
from unittest import TestCase, main

from lark import lark, Lark, UnexpectedToken, UnexpectedCharacters
from lark.load_grammar import GrammarError
from lark.lark_validator_visitor import LarkValidatorVisitor


# Test that certain previous differences between load_grammar.py and
# grammars/lark.lark have been resolved.
class TestIgnore(TestCase):
    def setUp(self):
        lark_path = os.path.join(os.path.dirname(lark.__file__), 'grammars/lark.lark')
        self.lark_parser = Lark.open(lark_path, parser="lalr")

    def test_load_grammar_import_multiple(self):
        g = """
            %ignore A B
            start: rule1
            rule1: "c"
            A: "a"
            B: "b"
        """
        l = Lark(g)
        self.assertRaisesRegex(UnexpectedCharacters, "No terminal matches 'b' in the current parser context", l.parse, "badbadbad")

    def test_lark_lark_ignore_multiple(self):
        g = """
            %ignore A B
            start: rule1
            rule1: "c"
            A: "a"
            B: "b"
        """
        t = self.lark_parser.parse(g)
        self.assertRaisesRegex(GrammarError, "Bad %ignore - must have a Terminal or other value", LarkValidatorVisitor.validate, t)


if __name__ == '__main__':
    main()
