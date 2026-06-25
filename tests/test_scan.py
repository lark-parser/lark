import unittest

from lark import Lark, TextSlice, Token, Transformer, Tree, ScanMatch
from lark.exceptions import ConfigurationError, LexError
from lark.indenter import Indenter


class TestScan(unittest.TestCase):
    def test_scan_sanity(self):
        for lexer in ["basic", "contextual"]:
            parser = Lark(r"""
            expr: "(" (WORD|expr)* ")"
            %ignore / +/
            WORD: /\w+/
            """, parser='lalr', start="expr", lexer=lexer)

            text = "|() | (a) | ((//)) | (c ((d))) |"
            finds = list(parser.scan(text))
            self.assertEqual(finds, [ScanMatch((1, 3), Tree('expr', [])),
                                    ScanMatch((6, 9), Tree('expr', ['a'])),
                                    ScanMatch((21, 30), Tree('expr', ['c', Tree('expr', [Tree('expr', ['d'])])])),
                                    ])

    def test_scan_meta(self):
        parser = Lark(r"""
        expr: "(" (WORD|expr)* ")"
        %ignore /\s+/
        WORD: /\w+/
        """, parser='lalr', start="expr", propagate_positions=True)

        text = " (a)\n(b)\n (\n)"
        finds = list(parser.scan(text))
        self.assertEqual(finds, [ScanMatch((1, 4), Tree('expr', ['a'])),
                                 ScanMatch((5, 8), Tree('expr', ['b'])),
                                 ScanMatch((10, 13), Tree('expr', []))])

        self.assertEqual(1, finds[0].value.meta.start_pos)
        self.assertEqual(4, finds[0].value.meta.end_pos)
        self.assertEqual(1, finds[0].value.meta.line)
        self.assertEqual(1, finds[0].value.meta.end_line)
        self.assertEqual(2, finds[0].value.meta.column)
        self.assertEqual(5, finds[0].value.meta.end_column)

        self.assertEqual(5, finds[1].value.meta.start_pos)
        self.assertEqual(8, finds[1].value.meta.end_pos)
        self.assertEqual(2, finds[1].value.meta.line)
        self.assertEqual(2, finds[1].value.meta.end_line)
        self.assertEqual(1, finds[1].value.meta.column)
        self.assertEqual(4, finds[1].value.meta.end_column)

        self.assertEqual(10, finds[2].value.meta.start_pos)
        self.assertEqual(13, finds[2].value.meta.end_pos)
        self.assertEqual(3, finds[2].value.meta.line)
        self.assertEqual(4, finds[2].value.meta.end_line)
        self.assertEqual(2, finds[2].value.meta.column)
        self.assertEqual(2, finds[2].value.meta.end_column)

    def test_scan_backtrack(self):
        """Tests that scan() returns the longest valid prefix when intermediate
        states also accept end-of-input."""

        parser = Lark(r"""
        start: expr+
        expr: "(" (WORD|expr)* ")"
        %ignore /\s+/
        WORD: /\w+/
        """, parser='lalr', start="start")

        text = "(a)(b) || (c)(d(e) || (f)"
        finds = list(parser.scan(text))
        self.assertEqual(finds, [
            ScanMatch((0, 6), Tree('start', [Tree('expr', ['a']), Tree('expr', ['b'])])),
            ScanMatch((10, 13), Tree('start', [Tree('expr', ['c'])])),
            ScanMatch((15, 18), Tree('start', [Tree('expr', ['e'])])),
            ScanMatch((22, 25), Tree('start', [Tree('expr', ['f'])])),
        ])

    def test_scan_subset(self):
        parser = Lark(r"""
        expr: "(" (WORD|expr)* ")"
        %ignore /\s+/
        WORD: /\w+/
        """, parser='lalr', start="expr", propagate_positions=True)

        text = "()\n()(a)\n(b)\n (\n) | \n(\n)"
        finds = list(parser.scan(TextSlice(text, 5, -1)))
        self.assertEqual(finds, [ScanMatch((5, 8), Tree('expr', ['a'])),
                                 ScanMatch((9, 12), Tree('expr', ['b'])),
                                 ScanMatch((14, 17), Tree('expr', []))])
        self.assertEqual(2, finds[0].value.meta.line)

        text = "()\n()(a)\n(b)\n (\n) | \n(\n)"
        finds = list(parser.scan(TextSlice(text, 5 - len(text), -1 + len(text))))
        self.assertEqual(finds, [ScanMatch((5, 8), Tree('expr', ['a'])),
                                 ScanMatch((9, 12), Tree('expr', ['b'])),
                                 ScanMatch((14, 17), Tree('expr', []))])
        self.assertEqual(2, finds[0].value.meta.line)

    def test_scan_requires_lalr(self):
        parser = Lark(r"""
        expr: "(" WORD ")"
        WORD: /\w+/
        """, parser='earley', start="expr")
        with self.assertRaises(ConfigurationError):
            list(parser.scan("(a)"))

    def test_scan_rejects_lexer_only(self):
        # A lexer-only Lark (parser=None) has no .parser; scan() must raise a clear
        # ConfigurationError, not leak an AttributeError.
        parser = Lark(r"""
        start: WORD
        WORD: /\w+/
        """, parser=None, lexer='basic')
        with self.assertRaises(ConfigurationError):
            list(parser.scan("a b c"))

    def test_scan_validates_eagerly(self):
        # scan() validates its configuration on the call itself, not lazily on first iteration.
        parser = Lark(r"""
        expr: "(" WORD ")"
        WORD: /\w+/
        """, parser='earley', start="expr")
        with self.assertRaises(ConfigurationError):
            parser.scan("(a)")  # not iterated — must still raise

    def test_scan_contextual(self):
        "Ensure a contextual scan works, where a basic scan would fail."

        grammar = r"""
        stmt: "let" NAME "=" NUMBER
        NAME: /\w+/
        NUMBER: /\d+/
        %ignore /\s+/
        """
        # In "let let = 5" the second `let` must lex as NAME, not the keyword.
        text = "garbage let let = 5 more"

        parser_ctx = Lark(grammar, parser='lalr', start='stmt')  # contextual (default)
        ctx_matches = list(parser_ctx.scan(text))
        self.assertEqual(len(ctx_matches), 1)
        self.assertEqual(ctx_matches[0].range, (8, 19))
        self.assertEqual(ctx_matches[0].value.children[0].value, 'let')

        # Sanity check: with the basic lexer the same input doesn't match
        parser_basic = Lark(grammar, parser='lalr', start='stmt', lexer='basic')
        self.assertEqual(list(parser_basic.scan(text)), [])

    def test_scan_lexer_callback_exception_skips_candidate(self):
        # A lexer-callback signalling an invalid token via ValueError must not
        # abort scan() — it should advance past the failing position and keep
        # searching for valid matches.
        def cb(t):
            if t.value == "bad":
                raise ValueError("user-callback boom")
            return t

        # Closed token vocabulary so scan can't find partial matches inside "bad".
        parser = Lark(r"""
        start: WORD+
        WORD: "bad" | "ok" | "good" | "pretty"
        %ignore /\s+/
        """, parser='lalr', lexer_callbacks={'WORD': cb})

        results = list(parser.scan("bad ok bad pretty good"))
        results2 = list(parser.scan("bad ok bad pretty good bad"))
        assert results == results2
        ranges = [m.range for m in results]
        values = [' '.join(c.value for c in m.value.children) for m in results]
        self.assertEqual(ranges, [(4, 6), (11, 22)])
        self.assertEqual(values, ["ok", "pretty good"])

    def test_scan_callback_dropping_positions_raises_clear_error(self):
        # If a user lexer_callback returns a fresh Token without copying source
        # positions, scan() should raise a clear LexError pointing at the cause
        # — not crash deep inside Scanner.search with an opaque TypeError.
        def cb(t):
            return Token(t.type, t.value.upper())  # drops positions

        parser = Lark(r"""
        start: WORD
        WORD: /\w+/
        """, parser='lalr', lexer_callbacks={'WORD': cb})

        with self.assertRaises(LexError) as cm:
            list(parser.scan("hello"))
        self.assertIn("did not preserve token positions", str(cm.exception))

    def test_scan_callback_dropping_positions_on_earlier_token_raises_clear_error(self):
        # The final token is enough to compute ScanMatch.range, but earlier tokens
        # still need positions for propagate_positions metadata.
        def cb(t):
            if t.value == "a":
                return Token(t.type, t.value)  # drops positions
            return t

        parser = Lark(r"""
        start: WORD WORD
        WORD: /[ab]/
        %ignore / +/
        """, parser='lalr', lexer_callbacks={'WORD': cb}, propagate_positions=True)

        with self.assertRaises(LexError) as cm:
            list(parser.scan("a b"))
        self.assertIn("did not preserve token positions", str(cm.exception))

    def test_scan_propagates_non_valueerror_callback_exception(self):
        # Non-ValueError exceptions from user callbacks are programming errors
        # and must surface — only ValueError is treated as "invalid token".
        def cb(t):
            raise RuntimeError("not a token-validity signal")

        parser = Lark(r"""
        start: WORD
        WORD: /\w+/
        """, parser='lalr', lexer_callbacks={'WORD': cb})

        with self.assertRaises(RuntimeError):
            list(parser.scan("hi"))

    def test_scan_does_not_swallow_configuration_error(self):
        # ConfigurationError subclasses ValueError, which scan() catches to skip a failed
        # lex. It must still propagate rather than being silently treated as "no match".
        def cb(t):
            raise ConfigurationError("boom")

        parser = Lark(r"""
        start: WORD
        WORD: /\w+/
        """, parser='lalr', lexer_callbacks={'WORD': cb})

        with self.assertRaises(ConfigurationError):
            list(parser.scan("hello"))

    def test_scan_returns_transformer_value(self):
        # ScanMatch.value is documented as "Tree, or whatever the transformer returns".
        class T(Transformer):
            def start(self, children):
                return sum(int(c) for c in children)

        parser = Lark(r"""
        start: NUMBER+
        NUMBER: /\d+/
        %ignore /\s+/
        """, parser='lalr', transformer=T())

        match, = parser.scan("1 2 3")
        self.assertEqual(match.range, (0, 5))
        self.assertEqual(match.value, 6)

    def test_scan_allows_non_deepcopyable_transformer(self):
        # scan() defers user callbacks to a single replay pass, so transformer values
        # that disable deepcopy still work — same constraint as parse().
        class NoCopy:
            def __init__(self, v): self.v = v
            def __deepcopy__(self, memo): raise TypeError("not deepcopyable")
            def __eq__(self, other): return isinstance(other, NoCopy) and self.v == other.v
            def __hash__(self): return hash(self.v)

        class T(Transformer):
            def A(self, t): return NoCopy(t.value)

        parser = Lark(r"""
        start: A+
        A: "a"
        """, parser='lalr', transformer=T())

        results = list(parser.scan("aa"))
        self.assertEqual(len(results), 1)
        match = results[0]
        self.assertEqual(match.range, (0, 2))
        self.assertEqual(match.value.children, [NoCopy("a"), NoCopy("a")])

    def test_scan_rejects_postlex(self):
        class MyIndenter(Indenter):
            NL_type = '_NL'
            OPEN_PAREN_types = []
            CLOSE_PAREN_types = []
            INDENT_type = '_INDENT'
            DEDENT_type = '_DEDENT'
            tab_len = 4

        parser = Lark(r"""
        start: NAME _NL+
        NAME: /\w+/
        _NL: /(\r?\n)+/
        %declare _INDENT _DEDENT
        """, parser='lalr', postlex=MyIndenter())
        # parse() should still work
        parser.parse("hi\n")
        # scan() must reject postlex with a clear ConfigurationError, not AttributeError.
        with self.assertRaises(ConfigurationError) as cm:
            list(parser.scan("hi\n"))
        self.assertIn("postlex", str(cm.exception).lower())


if __name__ == '__main__':
    unittest.main()
