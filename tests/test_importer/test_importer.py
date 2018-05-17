from lark.importer import LarkImporter

import unittest


"""
Module testing that the calc.lark grammar actually parses string as expected
"""

with LarkImporter():
    # This will build a lark instance
    if __package__ is not None:
        from . import calc
    else:  # running standalone
        import calc


class TestImporter(unittest.TestCase):
    def test_calc_add(self):

        assert calc.parser.parse("3 + 2", ).pretty() == """add
  number\t3
  number\t2
"""


    def test_calc_sub(self):

        assert calc.parser.parse("3 - 2", ).pretty() == """sub
  number\t3
  number\t2
"""


    def test_calc_mul(self):

        assert calc.parser.parse("3 * 2", ).pretty() == """mul
  number\t3
  number\t2
"""


    def test_calc_div(self):

        assert calc.parser.parse("3 / 2", ).pretty() == """div
  number\t3
  number\t2
"""


    def test_calc_assign(self):

        assert calc.parser.parse("b = 2", ).pretty() == """assign_var
  b
  number\t2
"""


if __name__ == '__main__':
    unittest.main()

