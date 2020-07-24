import json
import unittest
from lark import Lark
from lark.exceptions import GrammarError, ParseError, UnexpectedToken, UnexpectedInput, UnexpectedCharacters

class TestScopedIgnore(unittest.TestCase):
    def test_parse1(self):
        # Just a simple example of the grammar, to see that it parses
        l = Lark("""
            B: /b/
            %ignore /c/
            %scoped {
                %ignore B
                %unignore /c/
                start: "a" B "a"
            }
        """)
        l.parse("aba")
        l.parse("bbabbbabb")
        self.assertRaises(UnexpectedCharacters, l.parse, "abca")

    def test_parse2(self):
        l = Lark("""
            B: /b/
            %ignore B
            %scoped {
                %unignore B
                start: "a" "a"
            }
        """)
        l.parse("aa")
        self.assertRaises(UnexpectedCharacters, l.parse, "aba")

    def test_parse_fail_unignore(self):
        # Can't unignore something that isn't in the ignore set
        self.assertRaises(GrammarError, Lark, """
            %unignore /c/
            start: "a"
        """)

    def test_parse_unignore(self):
        # Unignoring works
        l = Lark("""
            B: /b/
            %ignore B
            rule1: "a" "a"
            %scoped {
                %unignore B
                start: rule1 "c" rule1
            }
        """)
        l.parse("abbbbacaba")
        l.parse("aacaa")
        self.assertRaises(UnexpectedCharacters, l.parse, "aabcaa")

    def test_parse_fail_unignore_alias(self):
        # Aliases don't count as the same
        self.assertRaises(GrammarError, Lark, """
            B: /b/
            %ignore /b/
            %scoped
            {
                %unignore B
                start: "foo"
            }
        """)

if __name__ == '__main__':
    unittest.main()
