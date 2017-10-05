from __future__ import absolute_import

import unittest
import logging
import os

logging.basicConfig(level=logging.INFO)

from lark.tools.nearley import create_code_for_nearley_grammar

NEARLEY_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), 'nearley'))
BUILTIN_PATH = os.path.join(NEARLEY_PATH, 'builtin')

class TestNearley(unittest.TestCase):
    def test_css(self):
        fn = os.path.join(NEARLEY_PATH, 'examples/csscolor.ne')
        with open(fn) as f:
            grammar = f.read()

        code = create_code_for_nearley_grammar(grammar, 'csscolor', BUILTIN_PATH, os.path.dirname(fn))
        d = {}
        exec (code, d)
        parse = d['parse']

        c = parse('#a199ff')
        assert c['r'] == 161
        assert c['g'] == 153
        assert c['b'] == 255

        c = parse('rgb(255, 70%, 3)')
        assert c['r'] == 255
        assert c['g'] == 178
        assert c['b'] == 3

    def test_include(self):
        fn = os.path.join(NEARLEY_PATH, 'test/grammars/folder-test.ne')
        with open(fn) as f:
            grammar = f.read()

        code = create_code_for_nearley_grammar(grammar, 'main', BUILTIN_PATH, os.path.dirname(fn))
        d = {}
        exec (code, d)
        parse = d['parse']

        parse('a')
        parse('b')

    def test_multi_include(self):
        fn = os.path.join(NEARLEY_PATH, 'test/grammars/multi-include-test.ne')
        with open(fn) as f:
            grammar = f.read()

        code = create_code_for_nearley_grammar(grammar, 'main', BUILTIN_PATH, os.path.dirname(fn))
        d = {}
        exec (code, d)
        parse = d['parse']

        parse('a')
        parse('b')
        parse('c')


if __name__ == '__main__':
    unittest.main()
