# -*- coding: utf-8 -*-
from __future__ import absolute_import

import logging
import unittest

logging.basicConfig(level=logging.INFO)

from lark.lark import Lark


class TestRegex(unittest.TestCase):
    def test_unicode_class(self):
        "Tests that character classes from the `regex` module work correctly."
        g = Lark(r"""
                    ?start: NAME
                    NAME: ID_START ID_CONTINUE*
                    ID_START: /[\p{Lu}\p{Ll}\p{Lt}\p{Lm}\p{Lo}\p{Nl}_]+/
                    ID_CONTINUE: ID_START | /[\p{Mn}\p{Mc}\p{Nd}\p{Pc}·]+/
                """)

        self.assertEqual(g.parse('வணக்கம்'), 'வணக்கம்')

    def test_unicode_word(self):
        "Tests that a persistent bug in the `re` module works when `regex` is enabled."
        g = Lark(r"""
                    ?start: NAME
                    NAME: /[\w]+/
                """)
        self.assertEqual(g.parse('வணக்கம்'), 'வணக்கம்')


if __name__ == '__main__':
    unittest.main()
