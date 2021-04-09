from __future__ import absolute_import

from unittest import TestCase, main

from lark import Lark, Tree, Transformer
from lark.lexer import Lexer, Token
import lark.lark as lark_module

try:
    from StringIO import StringIO
except ImportError:
    from io import BytesIO as StringIO


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


class TestT(Transformer):
    def add(self, children):
        return sum(children if isinstance(children, list) else children.children)

    def NUM(self, token):
        return int(token)


def append_zero(t):
    return t.update(value=t.value + '0')


class TestCache(TestCase):
    g = '''start: "a"'''

    
    def setUp(self):
        self.fs = lark_module.FS
        self.mock_fs = MockFS()
        lark_module.FS = self.mock_fs
        
    def tearDown(self):
        self.mock_fs.files = {}
        lark_module.FS = self.fs

    def test_simple(self):
        fn = "bla"

        Lark(self.g, parser='lalr', cache=fn)
        assert fn in self.mock_fs.files
        parser = Lark(self.g, parser='lalr', cache=fn)
        assert parser.parse('a') == Tree('start', [])
    
    def test_automatic_naming(self):
        assert len(self.mock_fs.files) == 0
        Lark(self.g, parser='lalr', cache=True)
        assert len(self.mock_fs.files) == 1
        parser = Lark(self.g, parser='lalr', cache=True)
        assert parser.parse('a') == Tree('start', [])

        parser = Lark(self.g + ' "b"', parser='lalr', cache=True)
        assert len(self.mock_fs.files) == 2
        assert parser.parse('ab') == Tree('start', [])

        parser = Lark(self.g, parser='lalr', cache=True)
        assert parser.parse('a') == Tree('start', [])
    
    def test_custom_lexer(self):

        parser = Lark(self.g, parser='lalr', lexer=CustomLexer, cache=True)
        parser = Lark(self.g, parser='lalr', lexer=CustomLexer, cache=True)
        assert len(self.mock_fs.files) == 1
        assert parser.parse('a') == Tree('start', [])

    def test_options(self):
        # Test options persistence
        Lark(self.g, parser="lalr", debug=True, cache=True)
        parser = Lark(self.g, parser="lalr", debug=True, cache=True)
        assert parser.options.options['debug']
    
    def test_inline(self):
        # Test inline transformer (tree-less) & lexer_callbacks
        g = """
        start: add+
        add: NUM "+" NUM
        NUM: /\d+/
        %ignore " "
        """
        text = "1+2 3+4"
        expected = Tree('start', [30, 70])

        parser = Lark(g, parser='lalr', transformer=TestT(), cache=True, lexer_callbacks={'NUM': append_zero})
        res0 = parser.parse(text)
        parser = Lark(g, parser='lalr', transformer=TestT(), cache=True, lexer_callbacks={'NUM': append_zero})
        assert len(self.mock_fs.files) == 1
        res1 = parser.parse(text)
        res2 = TestT().transform(Lark(g, parser="lalr", cache=True, lexer_callbacks={'NUM': append_zero}).parse(text))
        assert res0 == res1 == res2 == expected
    
    def test_imports(self):
        g = """
        %import .grammars.ab (startab, expr)
        """
        parser = Lark(g, parser='lalr', start='startab', cache=True)
        assert len(self.mock_fs.files) == 1
        parser = Lark(g, parser='lalr', start='startab', cache=True)
        assert len(self.mock_fs.files) == 1
        res = parser.parse("ab")
        self.assertEqual(res, Tree('startab', [Tree('expr', ['a', 'b'])]))
        
        


if __name__ == '__main__':
    main()
