from __future__ import absolute_import
import re

import os
from unittest import TestCase, main

from lark import Lark, Token, Tree, ParseError, UnexpectedInput
from lark.load_grammar import GrammarError, GRAMMAR_ERRORS, find_grammar_errors, list_grammar_imports
from lark.load_grammar import FromPackageLoader
from lark.lark_validator import LarkValidator


__all__ = ['TestGrammarLarkOnly']

class LarkDotLark:
    def __init__(self, grammar, **kwargs):
        options = {}
        options.update(kwargs)
        if "start" in options and options["start"] != "start":
            # We're not going to parse with the parser, so just override it.
            options["start"] = "start"
        lark_parser = Lark.open_from_package("lark", "grammars/lark.lark", **options)
        tree = lark_parser.parse(grammar)
        LarkValidator.validate(tree)

    def parse(self, text: str, start=None, on_error=None):
        raise Exception("Cannot test cases with lark.lark that try to parse using the tested grammar.")


# Test cases that LarkDotLark can't implement
class TestGrammarLarkOnly(TestCase):
    # Needs rewriting to work with lark.lark
    def test_errors(self):
        for msg, examples in GRAMMAR_ERRORS:
            for example in examples:
                with self.subTest(example=example):
                    self.assertRaisesRegex(GrammarError, re.escape(msg), Lark, example)

    # Cannot test cases with lark.lark that try to parse using the tested grammar. 
    def test_ignore_name(self):
        spaces = []
        p = Lark("""
            start: "a" "b"
            WS: " "
            %ignore WS
        """, parser='lalr', lexer_callbacks={'WS': spaces.append})
        assert p.parse("a b") == p.parse("a    b")
        assert len(spaces) == 5

    # Test fails for lark.lark because it does not execute %import.
    def test_override_rule1(self):
        # Overrides the 'sep' template in existing grammar to add an optional terminating delimiter
        # Thus extending it beyond its original capacity
        p = Lark("""
            %import .test_templates_import (start, sep)

            %override sep{item, delim}: item (delim item)* delim?
            %ignore " "
        """, source_path=__file__)

        a = p.parse('[1, 2, 3]')
        b = p.parse('[1, 2, 3, ]')
        assert a == b

    # Test fails for lark.lark because it does not execute %import.
    def test_override_rule2(self):
        self.assertRaisesRegex(GrammarError, "Rule 'delim' used but not defined \(in rule sep\)", Lark, """
            %import .test_templates_import (start, sep)

            %override sep{item}: item (delim item)* delim?
        """, source_path=__file__)

    # Test fails for lark.lark because it does not execute %import.
    def test_override_terminal(self):
        p = Lark("""

            %import .grammars.ab (startab, A, B)

            %override A: "c"
            %override B: "d"
        """, start='startab', source_path=__file__)

        a = p.parse('cd')
        self.assertEqual(a.children[0].children, [Token('A', 'c'), Token('B', 'd')])

    # Test fails for lark.lark because it does not execute %import.
    def test_extend_rule1(self):
        p = Lark("""
            %import .grammars.ab (startab, A, B, expr)

            %extend expr: B A
        """, start='startab', source_path=__file__)
        a = p.parse('abab')
        self.assertEqual(a.children[0].children, ['a', Tree('expr', ['b', 'a']), 'b'])

    # Test fails for lark.lark because it does not execute %import.
    def test_extend_term(self):
        p = Lark("""
            %import .grammars.ab (startab, A, B, expr)

            %extend A: "c"
        """, start='startab', source_path=__file__)
        a = p.parse('acbb')
        self.assertEqual(a.children[0].children, ['a', Tree('expr', ['c', 'b']), 'b'])

    # Cannot test cases with lark.lark that try to parse using the tested grammar. 
    def test_extend_twice(self):
        p = Lark("""
            start: x+

            x: "a"
            %extend x: "b"
            %extend x: "c"
        """)

        assert p.parse("abccbba") == p.parse("cbabbbb")

    # Test fails for lark.lark because it does not execute %import.
    def test_import_custom_sources1(self):
        custom_loader = FromPackageLoader(__name__, ('grammars', ))

        grammar = """
        start: startab

        %import ab.startab
        """

        p = Lark(grammar, import_paths=[custom_loader])
        self.assertEqual(p.parse('ab'),
                            Tree('start', [Tree('startab', [Tree('ab__expr', [Token('ab__A', 'a'), Token('ab__B', 'b')])])]))

    # Test fails for lark.lark because it does not execute %import.
    def test_import_custom_sources2(self):
        custom_loader = FromPackageLoader(__name__, ('grammars', ))

        grammar = """
        start: rule_to_import

        %import test_relative_import_of_nested_grammar__grammar_to_import.rule_to_import
        """
        p = Lark(grammar, import_paths=[custom_loader])
        x = p.parse('N')
        self.assertEqual(next(x.find_data('rule_to_import')).children, ['N'])

    # Test fails for lark.lark because it does not execute %import.
    def test_import_custom_sources3(self):
        custom_loader2 = FromPackageLoader(__name__)
        grammar = """
        %import .test_relative_import (start, WS)
        %ignore WS
        """
        p = Lark(grammar, import_paths=[custom_loader2], source_path=__file__) # import relative to current file
        x = p.parse('12 capybaras')
        self.assertEqual(x.children, ['12', 'capybaras'])

    # Test forces use of Lark.
    def test_find_grammar_errors1(self):
        text = """
        a: rule
        b rule
        c: rule
        B.: "hello" f
        D: "okay"
        """

        assert [e.line for e, _s in find_grammar_errors(text)] == [3, 5]

    # Test forces use of Lark.
    def test_find_grammar_errors2(self):
        text = """
        a: rule
        b rule
        | ok
        c: rule
        B.: "hello" f
        D: "okay"
        """

        assert [e.line for e, _s in find_grammar_errors(text)] == [3, 4, 6]

    # Test forces use of Lark.
    def test_find_grammar_errors3(self):
        text = """
        a: rule @#$#@$@&&
        b: rule
        | ok
        c: rule
        B: "hello" f @
        D: "okay"
        """

        x = find_grammar_errors(text)
        assert [e.line for e, _s in find_grammar_errors(text)] == [2, 6]

    # Cannot test cases with lark.lark that try to parse using the tested grammar. 
    def test_ranged_repeat_terms1(self):
        g = u"""!start: AAA
                AAA: "A"~3
            """
        l = Lark(g, parser='lalr')
        self.assertEqual(l.parse(u'AAA'), Tree('start', ["AAA"]))
        self.assertRaises((ParseError, UnexpectedInput), l.parse, u'AA')
        self.assertRaises((ParseError, UnexpectedInput), l.parse, u'AAAA')

    # Cannot test cases with lark.lark that try to parse using the tested grammar. 
    def test_ranged_repeat_terms2(self):
        g = u"""!start: AABB CC
                AABB: "A"~0..2 "B"~2
                CC: "C"~1..2
            """
        l = Lark(g, parser='lalr')
        self.assertEqual(l.parse(u'AABBCC'), Tree('start', ['AABB', 'CC']))
        self.assertEqual(l.parse(u'BBC'), Tree('start', ['BB', 'C']))
        self.assertEqual(l.parse(u'ABBCC'), Tree('start', ['ABB', 'CC']))
        self.assertRaises((ParseError, UnexpectedInput), l.parse, u'AAAB')
        self.assertRaises((ParseError, UnexpectedInput), l.parse, u'AAABBB')
        self.assertRaises((ParseError, UnexpectedInput), l.parse, u'ABB')
        self.assertRaises((ParseError, UnexpectedInput), l.parse, u'AAAABB')

    # Test depends on Lark.
    def test_ranged_repeat_large1(self):
        g = u"""!start: "A"~60
            """
        l = Lark(g, parser='lalr')
        self.assertGreater(len(l.rules), 1, "Expected that more than one rule will be generated")
        self.assertEqual(l.parse(u'A' * 60), Tree('start', ["A"] * 60))
        self.assertRaises(ParseError, l.parse, u'A' * 59)
        self.assertRaises((ParseError, UnexpectedInput), l.parse, u'A' * 61)

    # Cannot test cases with lark.lark that try to parse using the tested grammar. 
    def test_ranged_repeat_large2(self):
        g = u"""!start: "A"~15..100
            """
        l = Lark(g, parser='lalr')
        for i in range(0, 110):
            if 15 <= i <= 100:
                self.assertEqual(l.parse(u'A' * i), Tree('start', ['A']*i))
            else:
                self.assertRaises(UnexpectedInput, l.parse, u'A' * i)

    # Cannot test cases with lark.lark that try to parse using the tested grammar. 
    def test_ranged_repeat_large3(self):
        # 8191 is a Mersenne prime
        g = u"""start: "A"~8191
            """
        l = Lark(g, parser='lalr')
        self.assertEqual(l.parse(u'A' * 8191), Tree('start', []))
        self.assertRaises(UnexpectedInput, l.parse, u'A' * 8190)
        self.assertRaises(UnexpectedInput, l.parse, u'A' * 8192)

    # Cannot test cases with lark.lark that try to parse using the tested grammar. 
    def test_large_terminal(self):
        g = "start: NUMBERS\n"
        g += "NUMBERS: " + '|'.join('"%s"' % i for i in range(0, 1000))

        l = Lark(g, parser='lalr')
        for i in (0, 9, 99, 999):
            with self.subTest(i=i):
                self.assertEqual(l.parse(str(i)), Tree('start', [str(i)]))
        for i in (-1, 1000):
            with self.subTest(i=i):
                self.assertRaises(UnexpectedInput, l.parse, str(i))

    # Test forces use of Lark.
    def test_list_grammar_imports(self):
        grammar = """
        %import .test_templates_import (start, sep)

        %override sep{item, delim}: item (delim item)* delim?
        %ignore " "
        """

        imports = list_grammar_imports(grammar, [os.path.dirname(__file__)])
        self.assertEqual({os.path.split(i)[-1] for i in imports}, {'test_templates_import.lark', 'templates.lark'})

        imports = list_grammar_imports('%import common.WS', [])
        assert len(imports) == 1 and imports[0].pkg_name == 'lark'

    # Cannot test cases with lark.lark that try to parse using the tested grammar. 
    def test_line_breaks(self):
        p = Lark(r"""start: "a" \
                       "b"
                """)
        p.parse('ab')

# Tests that both Lark and LarkDotLark can implement
def _make_tests(parser):
    class _TestGrammar(TestCase):
        def test_empty_literal(self):
            # Issues #888
            self.assertRaisesRegex(GrammarError, "Empty terminals are not allowed \(\"\"\)", parser, "start: \"\"")

        def test_override_rule3(self):
            self.assertRaisesRegex(GrammarError, "Cannot override a nonexisting rule sep", parser, """
                %override sep{item}: item (delim item)* delim?
            """, source_path=__file__)

        def test_extend_rule2(self):
            self.assertRaisesRegex(GrammarError, "Can't extend rule expr as it wasn't defined before", parser, """
                %extend expr: B A
            """)

        def test_undefined_ignore1(self):
            g = """!start: "A"

                %ignore B
                """
            self.assertRaisesRegex( GrammarError, "Terminals {'B'} were marked to ignore but were not defined!", parser, g)

        def test_undefined_ignore2(self):
            g = """!start: "A"

                %ignore start
                """
            self.assertRaisesRegex( GrammarError, "Rules aren't allowed inside terminals ", parser, g)

        def test_alias_in_terminal(self):
            g = """start: TERM
                TERM: "a" -> alias
                """
            self.assertRaisesRegex( GrammarError, "Aliasing not allowed in terminals \(You used -> in the wrong place\)", parser, g)

        def test_undefined_rule(self):
            self.assertRaisesRegex(GrammarError, "Rule 'a' used but not defined \(in rule start\)", parser, """start: a""")

        def test_undefined_term(self):
            self.assertRaisesRegex(GrammarError, "Terminal 'A' used but not defined \(in rule start\)", parser, """start: A""")

        def test_token_multiline_only_works_with_x_flag(self):
            g = r"""start: ABC
                    ABC: /  a      b c
                                d
                                e f
                            /i
                        """
            self.assertRaisesRegex( GrammarError, "You can only use newlines in regular expressions with the `x` \(verbose\) flag", parser, g)

        def test_inline_with_expand_single(self):
            grammar = r"""
            start: _a
            !?_a: "A"
            """
            self.assertRaisesRegex(GrammarError, "Inlined rules \(_rule\) cannot use the \?rule modifier", parser, grammar)

        def test_declare_rule(self):
            g = """
            %declare a
            start: b
            b: "c"
            """
            self.assertRaisesRegex(GrammarError, "Expecting terminal name", parser, g)

        def test_declare_token(self):
            g = """
            %declare A
            start: b
            b: "c"
            """
            parser(g)

        def test_import_multiple(self):
            g = """
                %ignore A B
                start: rule1
                rule1: "c"
                A: "a"
                B: "b"
            """
            self.assertRaisesRegex(GrammarError, "Bad %ignore - must have a Terminal or other value", parser, g)

        def test_no_rule_aliases_below_top_level(self):
            g = """start: rule
                rule: ("a" -> alias
                     | "b")
                """
            self.assertRaisesRegex( GrammarError, "Rule 'alias' used but not defined", parser, g)

        def test_no_term_templates(self):
            g = """start: TERM
            separated{x, sep}: x (sep x)*
            TERM: separated{"A", " "}
            """
            self.assertRaisesRegex( GrammarError, "Templates not allowed in terminals", parser, g)

        def test_term_no_call_rule(self):
            g = """start: TERM
            TERM: rule
            rule: "a"
            """
            self.assertRaisesRegex( GrammarError, "Rules aren't allowed inside terminals", parser, g)

        def test_no_rule_modifiers_in_references(self):
            g = """start: rule1
                rule1: !?rule2
                rule2: "a"
            """
            self.assertRaisesRegex(GrammarError, "Expecting a value", Lark, g)

        def test_rule_modifier_query_bang(self):
            g = """start: rule1
                rule1: rule2
                ?!rule2: "a"
            """
            parser(g)

        def test_alias_top_level_ok(self):
            g = """
                start: rule1
                rule1: rule2 -> alias2
                rule2: "a"
            """
            parser(g)

        def test_terminal_alias_bad(self):
            g = """
                start: rule1
                rule1: TOKEN2
                TOKEN2: "a" -> alias2
            """
            self.assertRaisesRegex(GrammarError, "Aliasing not allowed in terminals", parser, g)

    _NAME = "TestGrammar" + parser.__name__
    _TestGrammar.__name__ = _NAME
    _TestGrammar.__qualname__ = _NAME
    globals()[_NAME] = _TestGrammar
    __all__.append(_NAME)


for parser in [Lark, LarkDotLark]:
    _make_tests(parser)

if __name__ == '__main__':
    main()
