from __future__ import absolute_import

import sys
import unittest
from unittest import TestCase

from lark.tree import Tree

from lark.tools import standalone

try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO




class TestStandalone(TestCase):
    def setUp(self):
        pass

    def _create_standalone(self, grammar):
        code_buf = StringIO()
        temp = sys.stdout
        sys.stdout = code_buf
        standalone.main(StringIO(grammar), 'start')
        sys.stdout = temp
        code = code_buf.getvalue()

        context = {}
        exec(code, context)
        return context

    def test_simple(self):
        grammar = """
            start: NUMBER WORD

            %import common.NUMBER
            %import common.WORD
            %import common.WS
            %ignore WS

        """

        context = self._create_standalone(grammar)

        _Lark = context['Lark_StandAlone']
        l = _Lark()
        x = l.parse('12 elephants')
        self.assertEqual(x.children, ['12', 'elephants'])

    def test_contextual(self):
        grammar = """
        start: a b
        a: "A" "B"
        b: "AB"
        """

        context = self._create_standalone(grammar)

        _Lark = context['Lark_StandAlone']
        l = _Lark()
        x = l.parse('ABAB')

        class T(context['Transformer']):
            def a(self, items):
                return 'a'
            def b(self, items):
                return 'b'
            start = list

        x = T().transform(x)
        self.assertEqual(x, ['a', 'b'])

        l2 = _Lark(transformer=T())
        x = l2.parse('ABAB')
        self.assertEqual(x, ['a', 'b'])

    def test_postlex(self):
        from lark.indenter import Indenter
        class MyIndenter(Indenter):
            NL_type = '_NEWLINE'
            OPEN_PAREN_types = ['LPAR', 'LSQB', 'LBRACE']
            CLOSE_PAREN_types = ['RPAR', 'RSQB', 'RBRACE']
            INDENT_type = '_INDENT'
            DEDENT_type = '_DEDENT'
            tab_len = 8

        grammar = r"""
            start:  "(" ")" _NEWLINE
            _NEWLINE: /\n/
        """

        # from lark import Lark
        # l = Lark(grammar, parser='lalr', lexer='contextual', postlex=MyIndenter())
        # x = l.parse('(\n)\n')
        # print('@@', x)


        context = self._create_standalone(grammar)
        _Lark = context['Lark_StandAlone']

        # l = _Lark(postlex=MyIndenter())
        # x = l.parse('()\n')
        # print(x)
        l = _Lark(postlex=MyIndenter())
        x = l.parse('(\n)\n')
        print(x)




if __name__ == '__main__':
    unittest.main()


