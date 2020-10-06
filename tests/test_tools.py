from __future__ import absolute_import, print_function

import sys
from unittest import TestCase, main

from lark import Lark
from lark.tree import Tree
from lark.tools import standalone

try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO




class TestStandalone(TestCase):
    def setUp(self):
        pass

    def _create_standalone(self, grammar, compress=False):
        code_buf = StringIO()
        standalone.gen_standalone(Lark(grammar, parser='lalr'), out=code_buf, compress=compress)
        code = code_buf.getvalue()

        context = {'__doc__': None}
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
        x = l.parse('16 candles')
        self.assertEqual(x.children, ['16', 'candles'])

        self.assertRaises(context['UnexpectedToken'], l.parse, 'twelve monkeys')
        self.assertRaises(context['UnexpectedToken'], l.parse, 'twelve')
        self.assertRaises(context['UnexpectedCharacters'], l.parse, '$ talks')

        context = self._create_standalone(grammar, compress=True)
        _Lark = context['Lark_StandAlone']
        l = _Lark()
        x = l.parse('12 elephants')

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

        context = self._create_standalone(grammar)
        _Lark = context['Lark_StandAlone']

        l = _Lark(postlex=MyIndenter())
        x = l.parse('()\n')
        self.assertEqual(x, Tree('start', []))
        l = _Lark(postlex=MyIndenter())
        x = l.parse('(\n)\n')
        self.assertEqual(x, Tree('start', []))

    def test_transformer(self):
        grammar = r"""
            start: some_rule "(" SOME_TERMINAL ")"
            some_rule: SOME_TERMINAL
            SOME_TERMINAL: /[A-Za-z_][A-Za-z0-9_]*/
        """
        context = self._create_standalone(grammar)
        _Lark = context["Lark_StandAlone"]

        _Token = context["Token"]
        _Tree = context["Tree"]

        class MyTransformer(context["Transformer"]):
            def SOME_TERMINAL(self, token):
                return _Token("SOME_TERMINAL", "token is transformed")

            def some_rule(self, children):
                return _Tree("rule_is_transformed", [])

        parser = _Lark(transformer=MyTransformer())
        self.assertEqual(
            parser.parse("FOO(BAR)"),
            _Tree("start", [
                _Tree("rule_is_transformed", []),
                _Token("SOME_TERMINAL", "token is transformed")
            ])
        )


if __name__ == '__main__':
    main()
