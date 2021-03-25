from __future__ import absolute_import

import sys
from unittest import TestCase, main

from lark import Lark, Tree, Transformer
from lark.lexer import Lexer, Token
import lark.lark as lark_module

try:
    from StringIO import StringIO
except ImportError:
    from io import BytesIO as StringIO

import tempfile, os

class TestT(Transformer):
    def add(self, children):
        return sum(children if isinstance(children, list) else children.children)

    def NUM(self, token):
        return int(token)


class MockFile(StringIO):
    def close(self):
        pass
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass

class MockFS:
    def __init__(self):
        self.files = {}

    def open(self, name, mode=None):
        if name not in self.files:
            f = self.files[name] = MockFile()
        else:
            f = self.files[name]
            f.seek(0)
        return f

    def exists(self, name):
        return name in self.files


class CustomLexer(Lexer):
    def __init__(self, lexer_conf):
        pass

    def lex(self, data):
        for obj in data:
            yield Token('A', obj)


class TestCache(TestCase):
    def setUp(self):
        pass

    def test_simple(self):
        g = '''start: "a"'''

        fn = "bla"

        fs = lark_module.FS
        mock_fs = MockFS()
        try:
            lark_module.FS = mock_fs
            Lark(g, parser='lalr', cache=fn)
            assert fn in mock_fs.files
            parser = Lark(g, parser='lalr', cache=fn)
            assert parser.parse('a') == Tree('start', [])

            mock_fs.files = {}
            assert len(mock_fs.files) == 0
            Lark(g, parser='lalr', cache=True)
            assert len(mock_fs.files) == 1
            parser = Lark(g, parser='lalr', cache=True)
            assert parser.parse('a') == Tree('start', [])

            parser = Lark(g+' "b"', parser='lalr', cache=True)
            assert len(mock_fs.files) == 2
            assert parser.parse('ab') == Tree('start', [])

            parser = Lark(g, parser='lalr', cache=True)
            assert parser.parse('a') == Tree('start', [])

            # Test with custom lexer
            mock_fs.files = {}
            parser = Lark(g, parser='lalr', lexer=CustomLexer, cache=True)
            parser = Lark(g, parser='lalr', lexer=CustomLexer, cache=True)
            assert len(mock_fs.files) == 1
            assert parser.parse('a') == Tree('start', [])

            # Test options persistence
            mock_fs.files = {}
            Lark(g, parser="lalr", debug=True, cache=True)
            parser = Lark(g, parser="lalr", debug=True, cache=True)
            assert parser.options.options['debug']

            # Test inline transformer (tree-less)
            mock_fs.files = {}
            g = """
            start: add+
            add: NUM "+" NUM
            NUM: /\d+/
            %ignore " "
            """
            text = "1+2 3+4"
            expected = Tree('start', [3, 7])

            parser = Lark(g, parser='lalr', transformer=TestT(), cache=True)
            parser = Lark(g, parser='lalr', transformer=TestT(), cache=True)
            assert len(mock_fs.files) == 1
            res1 = parser.parse(text)
            res2 = TestT().transform( Lark(g, parser="lalr", cache=True).parse(text) )
            assert res1 == res2

        finally:
            lark_module.FS = fs



if __name__ == '__main__':
    main()
