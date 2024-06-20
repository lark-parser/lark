import unittest

from lark import Lark, Tree


class TestScan(unittest.TestCase):
    def test_scan(self):
        parser = Lark(r"""
        expr: "(" (WORD|expr)* ")"
        %ignore / +/
        WORD: /\w+/
        """, parser='lalr', start="expr")

        text = "|() | (a) | ((//)) | (c ((d))) |"
        finds = list(parser.scan(text))
        self.assertEqual(finds, [((1, 3), Tree('expr', [])),
                                 ((6, 9), Tree('expr', ['a'])),
                                 ((21, 30), Tree('expr', ['c', Tree('expr', [Tree('expr', ['d'])])])),
                                 ])

    def test_scan_basic_lexer(self):
        parser = Lark(r"""
        expr: "(" (WORD|expr)* ")"
        %ignore / +/
        WORD: /\w+/
        """, parser='lalr', start="expr", lexer='basic')

        text = "|() | (a) | ((//)) | (c ((d))) |"
        finds = list(parser.scan(text))
        self.assertEqual(finds, [((1, 3), Tree('expr', [])),
                                 ((6, 9), Tree('expr', ['a'])),
                                 ((21, 30), Tree('expr', ['c', Tree('expr', [Tree('expr', ['d'])])])),
                                 ])

    def test_scan_meta(self):
        parser = Lark(r"""
        expr: "(" (WORD|expr)* ")"
        %ignore /\s+/
        WORD: /\w+/
        """, parser='lalr', start="expr", propagate_positions=True)

        text = " (a)\n(b)\n (\n)"
        finds = list(parser.scan(text))
        self.assertEqual(finds, [((1, 4), Tree('expr', ['a'])),
                                 ((5, 8), Tree('expr', ['b'])),
                                 ((10, 13), Tree('expr', []))])

        self.assertEqual(1, finds[0][1].meta.start_pos)
        self.assertEqual(4, finds[0][1].meta.end_pos)
        self.assertEqual(1, finds[0][1].meta.line)
        self.assertEqual(1, finds[0][1].meta.end_line)
        self.assertEqual(2, finds[0][1].meta.column)
        self.assertEqual(5, finds[0][1].meta.end_column)

        self.assertEqual(5, finds[1][1].meta.start_pos)
        self.assertEqual(8, finds[1][1].meta.end_pos)
        self.assertEqual(2, finds[1][1].meta.line)
        self.assertEqual(2, finds[1][1].meta.end_line)
        self.assertEqual(1, finds[1][1].meta.column)
        self.assertEqual(4, finds[1][1].meta.end_column)

        self.assertEqual(10, finds[2][1].meta.start_pos)
        self.assertEqual(13, finds[2][1].meta.end_pos)
        self.assertEqual(3, finds[2][1].meta.line)
        self.assertEqual(4, finds[2][1].meta.end_line)
        self.assertEqual(2, finds[2][1].meta.column)
        self.assertEqual(2, finds[2][1].meta.end_column)

    def test_scan_backtrack(self):
        """ Tests that the scan function properly backtracks if it finds partial, but incorrect parses"""

        parser = Lark(r"""
        start: expr+
        expr: "(" (WORD|expr)* ")"
        %ignore /\s+/
        WORD: /\w+/
        """, parser='lalr', start="start")

        text = "(a)(b) || (c)(d(e) || (f)"
        finds = list(parser.scan(text))
        self.assertEqual(finds, [
            ((0, 6), Tree('start', [Tree('expr', ['a']), Tree('expr', ['b'])])),
            ((10, 13), Tree('start', [Tree('expr', ['c'])])),
            ((15, 18), Tree('start', [Tree('expr', ['e'])])),
            ((22, 25), Tree('start', [Tree('expr', ['f'])])),
        ])

    def test_scan_subset(self):
        parser = Lark(r"""
        expr: "(" (WORD|expr)* ")"
        %ignore /\s+/
        WORD: /\w+/
        """, parser='lalr', start="expr", propagate_positions=True)

        text = "()\n()(a)\n(b)\n (\n) | \n(\n)"
        finds = list(parser.scan(text, start_pos=5, end_pos=-1))
        self.assertEqual(finds, [((5, 8), Tree('expr', ['a'])),
                                 ((9, 12), Tree('expr', ['b'])),
                                 ((14, 17), Tree('expr', []))])
        self.assertEqual(2, finds[0][1].meta.line)

        text = "()\n()(a)\n(b)\n (\n) | \n(\n)"
        finds = list(parser.scan(text, start_pos=5-len(text), end_pos=-1+len(text)))
        self.assertEqual(finds, [((5, 8), Tree('expr', ['a'])),
                                 ((9, 12), Tree('expr', ['b'])),
                                 ((14, 17), Tree('expr', []))])
        self.assertEqual(2, finds[0][1].meta.line)
