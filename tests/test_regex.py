# -*- coding: utf-8 -*-
from __future__ import absolute_import

import logging
import sys
import unittest

logging.basicConfig(level=logging.INFO)

from lark.lark import Lark


class TestRegex(unittest.TestCase):
    @unittest.skipIf(sys.version_info[0] == 2, 'Unicode and Python 2 do not place nicely together.')
    def test_unicode_class(self):
        "Tests that character classes from the `regex` module work correctly."
        g = Lark(r"""
                    ?start: NAME
                    NAME: ID_START ID_CONTINUE*
                    ID_START: /[\p{Lu}\p{Ll}\p{Lt}\p{Lm}\p{Lo}\p{Nl}_]+/
                    ID_CONTINUE: ID_START | /[\p{Mn}\p{Mc}\p{Nd}\p{Pc}·]+/
                """, regex=True)

        self.assertEqual(g.parse('வணக்கம்'), 'வணக்கம்')

    @unittest.skipIf(sys.version_info[0] == 2, 'Unicode and Python 2 do not place nicely together.')
    def test_unicode_word(self):
        "Tests that a persistent bug in the `re` module works when `regex` is enabled."
        g = Lark(r"""
                    ?start: NAME
                    NAME: /[\w]+/
                """, regex=True)
        self.assertEqual(g.parse('வணக்கம்'), 'வணக்கம்')


if __name__ == '__main__':
    unittest.main()
