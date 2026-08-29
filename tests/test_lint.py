import unittest
import sys
from io import StringIO
from lark.tools.lint import lint_grammar

class TestLinter(unittest.TestCase):
    def test_clean_grammar(self):
        grammar = """
        start: a b
        a: "A"
        b: "B"
        """
        self.assertEqual(lint_grammar(grammar), 0)

    def test_unused_rule(self):
        grammar = """
        start: a
        a: "A"
        unused_rule: "U"
        """
        captured_output = StringIO()
        sys.stdout = captured_output
        warnings = lint_grammar(grammar)
        sys.stdout = sys.__stdout__
        
        self.assertEqual(warnings, 1)
        self.assertIn("Unused rule 'unused_rule'", captured_output.getvalue())

    def test_unused_terminal(self):
        grammar = """
        start: a
        a: "A"
        UNUSED_TERM: "U"
        """
        captured_output = StringIO()
        sys.stdout = captured_output
        warnings = lint_grammar(grammar)
        sys.stdout = sys.__stdout__
        
        self.assertEqual(warnings, 1)
        self.assertIn("Unused terminal 'UNUSED_TERM'", captured_output.getvalue())

    def test_undefined_rule(self):
        grammar = """
        start: a b
        a: "A"
        """
        captured_output = StringIO()
        sys.stdout = captured_output
        warnings = lint_grammar(grammar)
        sys.stdout = sys.__stdout__
        
        self.assertEqual(warnings, 1)
        self.assertIn("Rule 'b' used but not defined", captured_output.getvalue())

    def test_undefined_terminal(self):
        grammar = """
        start: a UNDEF
        a: "A"
        """
        captured_output = StringIO()
        sys.stdout = captured_output
        warnings = lint_grammar(grammar)
        sys.stdout = sys.__stdout__
        
        self.assertEqual(warnings, 1)
        self.assertIn("Rule 'UNDEF' used but not defined", captured_output.getvalue())

    def test_ignore(self):
        grammar = """
        start: a
        a: "A"
        WS: /[ \\t\\f\\r\\n]/
        %ignore WS
        """
        captured_output = StringIO()
        sys.stdout = captured_output
        warnings = lint_grammar(grammar)
        sys.stdout = sys.__stdout__
        
        self.assertEqual(warnings, 0)
