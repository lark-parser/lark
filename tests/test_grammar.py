from __future__ import absolute_import

import sys
from unittest import TestCase, main

from lark import Lark
from lark.load_grammar import GrammarLoader, GrammarError


class TestGrammar(TestCase):
    def setUp(self):
        pass

    def test_errors(self):
        for msg, examples in GrammarLoader.ERRORS:
            for example in examples:
                try:
                    p = Lark(example)
                except GrammarError as e:
                    assert msg in str(e)
                else:
                    assert False, "example did not raise an error"




if __name__ == '__main__':
    main()



