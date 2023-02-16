from unittest import TestCase, main

from lark import Token


class TestPatternMatching(TestCase):
    token = Token('A', 'a')

    def setUp(self):
        pass

    def test_matches_with_string(self):
        match self.token:
            case 'a':
                pass
            case _:
                assert False

    def test_matches_with_str_positional_arg(self):
        match self.token:
            case str('a'):
                pass
            case _:
                assert False

    def test_matches_with_token_positional_arg(self):
        match self.token:
            case Token('a'):
                assert False
            case Token('A'):
                pass
            case _:
                assert False

    def test_matches_with_token_kwarg_type(self):
        match self.token:
            case Token(type='A'):
                pass
            case _:
                assert False

    def test_matches_with_bad_token_type(self):
        match self.token:
            case Token(type='B'):
                assert False
            case _:
                pass



if __name__ == '__main__':
    main()
