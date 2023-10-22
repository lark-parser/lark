from __future__ import absolute_import, print_function

from unittest import TestCase, main

from lark import Lark
from lark.tree import Tree
from lark.tools import standalone

from io import StringIO


class TestStandalone(TestCase):
    def setUp(self):
        pass

    def _create_standalone(self, grammar, compress=False):
        code_buf = StringIO()
        standalone.gen_standalone(Lark(grammar, parser='lalr'), out=code_buf, compress=compress)
        code = code_buf.getvalue()

        context = {'__doc__': None, '__name__': 'test_standalone'}
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

    def test_interactive(self):
        grammar = """
                start: A+ B*
                A: "a"
                B: "b"
        """
        context = self._create_standalone(grammar)
        parser: Lark = context['Lark_StandAlone']()

        ip = parser.parse_interactive()

        UnexpectedToken = context['UnexpectedToken']
        Token = context['Token']

        self.assertRaises(UnexpectedToken, ip.feed_eof)
        self.assertRaises(TypeError, ip.exhaust_lexer)
        ip.feed_token(Token('A', 'a'))
        res = ip.feed_eof()
        self.assertEqual(res, Tree('start', ['a']))

        ip = parser.parse_interactive("ab")

        ip.exhaust_lexer()

        ip_copy = ip.copy()
        self.assertEqual(ip_copy.parser_state, ip.parser_state)
        self.assertEqual(ip_copy.lexer_thread.state, ip.lexer_thread.state)
        self.assertIsNot(ip_copy.parser_state, ip.parser_state)
        self.assertIsNot(ip_copy.lexer_thread.state, ip.lexer_thread.state)
        self.assertIsNot(ip_copy.lexer_thread.state.line_ctr, ip.lexer_thread.state.line_ctr)

        res = ip.feed_eof(ip.lexer_thread.state.last_token)
        self.assertEqual(res, Tree('start', ['a', 'b']))
        self.assertRaises(UnexpectedToken, ip.feed_eof)

        self.assertRaises(UnexpectedToken, ip_copy.feed_token, Token('A', 'a'))
        ip_copy.feed_token(Token('B', 'b'))
        res = ip_copy.feed_eof()
        self.assertEqual(res, Tree('start', ['a', 'b', 'b']))

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

        _v_args = context['v_args']
        @_v_args(inline=True)
        class T(context['Transformer']):
            def a(self):
                return 'a'
            def b(self):
                return 'b'

            start = _v_args(inline=False)(list)

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
