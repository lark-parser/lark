from lark import Lark
from lark.lark_validator import LarkValidator
from unittest import TestCase, main, SkipTest

class TestLarkValidator(TestCase):
    def test_example(self):
        my_grammar = """
            start: "A"
        """
        lark_parser = Lark.open_from_package("lark", "grammars/lark.lark", parser="lalr")
        parse_tree = lark_parser.parse(my_grammar)
        LarkValidator.validate(parse_tree)