from unittest import TestCase, main

from lark import Lark
from lark.indenter import PythonIndenter
from lark.exceptions import UnexpectedCharacters


python_parser = Lark.open_from_package(
    "lark", "python.lark", ["grammars"], parser='lalr', postlex=PythonIndenter(),
    start=["number", "DEC_NUMBER", "HEX_NUMBER", "OCT_NUMBER",
           "BIN_NUMBER", "FLOAT_NUMBER", "IMAG_NUMBER"])

valid_DEC_NUMBER = [
    "0",
    "000",
    "0_0_0",
    "4_2",
    "1_0000_0000",
    "123456789012345678901234567890",
]

valid_HEX_NUMBER = [
    "0x_f",
    "0xffff_ffff",
    "0xffffffffffffffff",
    "0Xffffffffffffffff",
]

valid_OCT_NUMBER = [
    "0o5_7_7",
    "0o_5",
    "0o77777777777777777",
    "0O77777777777777777",
]
    
valid_BIN_NUMBER = [
    "0b1001_0100",
    "0b_0",
    "0b100000000000000000000000000000000000000000000000000000000000000000000",
    "0B111111111111111111111111111111111111111111111111111111111111111111111",
]

valid_FLOAT_NUMBER = [
    "1_00_00.5",
    "1_00_00.5e5",
    "1_00_00e5_1",
    "1e1_0",
    ".1_4",
    ".1_4e1",
    "1_2.5",
    "3.14",
    "314.",
    "0.314",
    "000.314",
    ".314",
    "3e14",
    "3E14",
    "3e-14",
    "3e+14",
    "3.e14",
    ".3e14",
    "3.1e4",
]

valid_IMAG_NUMBER = [
    "0j",
    "123456789012345678901234567890j",
    "1_00_00j",
    "1_00_00.5j",
    "1_00_00e5_1j",
    ".1_4j",
    "3_3j",
    ".5_6j",
    "3.14j",
    "314.j",
    "0.314j",
    "000.314j",
    ".314j",
    "3e14j",
    "3E14j",
    "3e-14j",
    "3e+14j",
    "3.e14j",
    ".3e14j",
    "3.1e4j",
]

valid_number = (valid_DEC_NUMBER + valid_HEX_NUMBER + valid_OCT_NUMBER +
                valid_BIN_NUMBER + valid_FLOAT_NUMBER + valid_IMAG_NUMBER)


invalid_number = [
    "0_",
    "42_",
    "1.4j_",
    "0x_",
    "0b1_",
    "0xf_",
    "0o5_",
    "1_Else",
    "0_b0",
    "0_xf",
    "0_o5",
    "0_7",
    "09_99",
    "4_______2",
    "0.1__4",
    "0.1__4j",
    "0b1001__0100",
    "0xffff__ffff",
    "0x___",
    "0o5__77",
    "1e1__0",
    "1e1__0j",
    "1_.4",
    "1_.4j",
    "1._4",
    "1._4j",
    "._5",
    "._5j",
    "1.0e+_1",
    "1.0e+_1j",
    "1.4_j",
    "1.4e5_j",
    "1_e1",
    "1.4_e1",
    "1.4_e1j",
    "1e_1",
    "1.4e_1",
    "1.4e_1j",
    "1+1.5_j_",
    "1+1.5_j",

    "_0",
    "_42",
    "_1.4j",
    "_0x",
    "_0b1",
    "_0xf",
    "_0o5",
    "_1_Else",
    "_0_b0",
    "_0_xf",
    "_0_o5",
    "_0_7",
    "_09_99",
    "_4_______2",
    "_0.1__4",
    "_0.1__4j",
    "_0b1001__0100",
    "_0xffff__ffff",
    "_0x__",
    "_0o5__77",
    "_1e1__0",
    "_1e1__0j",
    "_1_.4",
    "_1_.4j",
    "_1._4",
    "_1._4j",
    "_._5",
    "_._5j",
    "_1.0e+_1",
    "_1.0e+_1j",
    "_1.4_j",
    "_1.4e5_j",
    "_1_e1",
    "_1.4_e1",
    "_1.4_e1j",
    "_1e_1",
    "_1.4e_1",
    "_1.4e_1j",
    "_1+1.5_j",
    "_1+1.5_j",
]


class TestPythonParser(TestCase):
    def test_DEC_NUMBER(self):
        for case in valid_DEC_NUMBER:
            python_parser.parse(case, start="DEC_NUMBER")  # no error

    def test_HEX_NUMBER(self):
        for case in valid_HEX_NUMBER:
            python_parser.parse(case, start="HEX_NUMBER")  # no error

    def test_OCT_NUMBER(self):
        for case in valid_OCT_NUMBER:
            python_parser.parse(case, start="OCT_NUMBER")  # no error

    def test_BIN_NUMBER(self):
        for case in valid_BIN_NUMBER:
            python_parser.parse(case, start="BIN_NUMBER")  # no error

    def test_FLOAT_NUMBER(self):
        for case in valid_FLOAT_NUMBER:
            python_parser.parse(case, start="FLOAT_NUMBER")  # no error

    def test_IMAG_NUMBER(self):
        for case in valid_IMAG_NUMBER:
            python_parser.parse(case, start="IMAG_NUMBER")  # no error

    def test_number(self):
        for case in valid_number:
            python_parser.parse(case, start="number")  # no error

        for case in invalid_number:
            with self.assertRaises(UnexpectedCharacters):
                python_parser.parse(case, start="number")  # no error

if __name__ == '__main__':
    main()
