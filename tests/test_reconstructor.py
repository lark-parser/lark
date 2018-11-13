import json
import unittest
from unittest import TestCase
from lark import Lark
from lark.reconstruct import Reconstructor


common = """
%import common (WS_INLINE, NUMBER, WORD)
%ignore WS_INLINE
"""

def _remove_ws(s):
    return s.replace(' ', '').replace('\n','')

class TestReconstructor(TestCase):

    def assert_reconstruct(self, grammar, code):
        parser = Lark(grammar, parser='lalr')
        tree = parser.parse(code)
        new = Reconstructor(parser).reconstruct(tree)
        self.assertEqual(_remove_ws(code), _remove_ws(new))

    def test_starred_rule(self):

        g = """
        start: item*
        item: NL
            | rule
        rule: WORD ":" NUMBER
        NL: /(\\r?\\n)+\s*/
        """ + common

        code = """
        Elephants: 12
        """

        self.assert_reconstruct(g, code)

    def test_starred_group(self):

        g = """
        start: (rule | NL)*
        rule: WORD ":" NUMBER
        NL: /(\\r?\\n)+\s*/
        """ + common

        code = """
        Elephants: 12
        """

        self.assert_reconstruct(g, code)

    def test_alias(self):

        g = """
        start: line*
        line: NL
            | rule
            | "hello" -> hi
        rule: WORD ":" NUMBER
        NL: /(\\r?\\n)+\s*/
        """ + common

        code = """
        Elephants: 12
        hello
        """

        self.assert_reconstruct(g, code)

    def test_json_example(self):
        test_json = '''
            {
                "empty_object" : {},
                "empty_array"  : [],
                "booleans"     : { "YES" : true, "NO" : false },
                "numbers"      : [ 0, 1, -2, 3.3, 4.4e5, 6.6e-7 ],
                "strings"      : [ "This", [ "And" , "That", "And a \\"b" ] ],
                "nothing"      : null
            }
        '''

        json_grammar = r"""
            ?start: value

            ?value: object
                  | array
                  | string
                  | SIGNED_NUMBER      -> number
                  | "true"             -> true
                  | "false"            -> false
                  | "null"             -> null

            array  : "[" [value ("," value)*] "]"
            object : "{" [pair ("," pair)*] "}"
            pair   : string ":" value

            string : ESCAPED_STRING

            %import common.ESCAPED_STRING
            %import common.SIGNED_NUMBER
            %import common.WS

            %ignore WS
        """

        json_parser = Lark(json_grammar, parser='lalr')
        tree = json_parser.parse(test_json)

        new_json = Reconstructor(json_parser).reconstruct(tree)
        self.assertEqual(json.loads(new_json), json.loads(test_json))


if __name__ == '__main__':
    unittest.main()
