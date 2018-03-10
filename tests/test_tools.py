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

    def test_simple(self):
        grammar = """
            start: NUMBER WORD

            %import common.NUMBER
            %import common.WORD
            %import common.WS
            %ignore WS

        """

        code_buf = StringIO()
        temp = sys.stdout
        sys.stdout = code_buf
        standalone.main(StringIO(grammar), 'start')
        sys.stdout = temp
        code = code_buf.getvalue()

        context = {}
        exec(code, context)
        _Lark = context['Lark_StandAlone']

        l = _Lark()
        x = l.parse('12 elephants')
        self.assertEqual(x.children, ['12', 'elephants'])


if __name__ == '__main__':
    unittest.main()


