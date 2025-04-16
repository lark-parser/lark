from unittest import TestCase, main

from lark import Token, Tree


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

    def test_match_on_tree(self):
        tree1 = Tree('a', [Tree(x, y) for x, y in zip('bcd', 'xyz')])
        tree2 = Tree('a', [
            Tree('b', [Token('T', 'x')]),
            Tree('c', [Token('T', 'y')]),
            Tree('d', [Tree('z', [Token('T', 'zz'), Tree('zzz', 'zzz')])]),
        ])

        match tree1:
            case Tree('X', []):
                assert False
            case Tree('a', []):
                assert False
            case Tree(_, 'b'):
                assert False
            case Tree('X', _):
                assert False
        tree = Tree('q', [Token('T', 'x')])
        match tree:
            case Tree('q', [Token('T', 'x')]):
                pass
            case _:
                assert False
        tr = Tree('a', [Tree('b', [Token('T', 'a')])])
        match tr:
            case Tree('a', [Tree('b', [Token('T', 'a')])]):
                pass
            case _:
                assert False
        # test nested trees
        match tree2:
            case Tree('a', [
                    Tree('b', [Token('T', 'x')]),
                    Tree('c', [Token('T', 'y')]),
                    Tree('d', [
                        Tree('z', [
                            Token('T', 'zz'),
                            Tree('zzz', 'zzz')
                        ])
                    ])
            ]):
                pass
            case _:
                assert False



if __name__ == '__main__':
    main()
