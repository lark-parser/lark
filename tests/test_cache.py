from __future__ import absolute_import

import sys
from unittest import TestCase, main

from lark import Lark, Tree
import lark.lark as lark_module

try:
    from StringIO import StringIO
except ImportError:
    from io import BytesIO as StringIO

import tempfile, os


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

        finally:
            lark_module.FS = fs



if __name__ == '__main__':
    main()



