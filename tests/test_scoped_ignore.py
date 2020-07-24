import json
import unittest
from lark import Lark
from lark.exceptions import GrammarError, ParseError, UnexpectedToken, UnexpectedInput, UnexpectedCharacters

class TestScopedIgnore(unittest.TestCase):
    def test_parse1(self):
        # Just a simple example of the grammar, to see that it parses
        Lark("""
            B: /b/
            %ignore /aaa/
            %scoped {
                %ignore B
                %unignore /aaa/
                start: "a" B "a"
            }
        """)

    def test_parse2(self):
        # Just a simple example of the grammar, to see that it parses
        Lark("""
            B: /b/
            %ignore B
            %scoped {
                %unignore B
                start: "a" "a"
            }
        """)

    def test_parse_fail_remove(self):
        # Can't unignore something that isn't in the ignore set
        g = """
            %unignore /c/
            start: "a"
        """
        self.assertRaises(GrammarError, Lark, g)

    def test_parse_unignore(self):
        # Unignoring works
        Lark("""
            B: /b/
            %ignore B
            rule1: "a" "a"
            %scoped {
                %unignore B
                start: rule1 "c" rule1
            }
        """)
        # Should match abbbbacaba, aacaa, but not aabcaa

    def test_parse_fail_remove_alias(self):
        # Aliases don't count as the same
        g = """
            B: /b/
            %ignore /b/
            %scoped
            {
                %unignore B
                start: "foo"
            }
        """
        self.assertRaises(GrammarError, Lark, g)

if __name__ == '__main__':
    unittest.main()
