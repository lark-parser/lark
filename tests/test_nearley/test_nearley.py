from __future__ import absolute_import

import unittest
import logging
import os
import sys

logging.basicConfig(level=logging.INFO)

from lark.tools.nearley import create_code_for_nearley_grammar

NEARLEY_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), 'nearley'))
BUILTIN_PATH = os.path.join(NEARLEY_PATH, 'builtin')

class TestNearley(unittest.TestCase):
    def test_css(self):
        css_example_grammar = """
        # http://www.w3.org/TR/css3-color/#colorunits

        @builtin "whitespace.ne"
        @builtin "number.ne"
        @builtin "postprocessors.ne"

        csscolor -> "#" hexdigit hexdigit hexdigit hexdigit hexdigit hexdigit {%
            function(d) {
                return {
                    "r": parseInt(d[1]+d[2], 16),
                    "g": parseInt(d[3]+d[4], 16),
                    "b": parseInt(d[5]+d[6], 16),
                }
            }
        %}
                  | "#" hexdigit hexdigit hexdigit {%
            function(d) {
                return {
                    "r": parseInt(d[1]+d[1], 16),
                    "g": parseInt(d[2]+d[2], 16),
                    "b": parseInt(d[3]+d[3], 16),
                }
            }
        %}
                  | "rgb"  _ "(" _ colnum _ "," _ colnum _ "," _ colnum _ ")" {% $({"r": 4, "g": 8, "b": 12}) %}
                  | "hsl"  _ "(" _ colnum _ "," _ colnum _ "," _ colnum _ ")" {% $({"h": 4, "s": 8, "l": 12}) %}
                  | "rgba" _ "(" _ colnum _ "," _ colnum _ "," _ colnum _ "," _ decimal _ ")" {% $({"r": 4, "g": 8, "b": 12, "a": 16}) %}
                  | "hsla" _ "(" _ colnum _ "," _ colnum _ "," _ colnum _ "," _ decimal _ ")" {% $({"h": 4, "s": 8, "l": 12, "a": 16}) %}

        hexdigit -> [a-fA-F0-9]
        colnum -> unsigned_int {% id %} | percentage {%
            function(d) {return Math.floor(d[0]*255); }
        %}
        """

        code = create_code_for_nearley_grammar(css_example_grammar, 'csscolor', BUILTIN_PATH, './')
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


if __name__ == '__main__':
    unittest.main()
