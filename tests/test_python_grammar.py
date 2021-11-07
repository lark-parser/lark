from unittest import TestCase, main

from lark import Lark
from lark.indenter import PythonIndenter


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


if __name__ == '__main__':
    main()
