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
                self.fail("Token did not match the expected string pattern")

    def test_matches_with_str_positional_arg(self):
        match self.token:
            case str('a'):
                pass
            case _:
                self.fail("Token did not match the expected str pattern")

    def test_matches_with_token_positional_arg(self):
        match self.token:
            case Token('a'):
                self.fail("Token unexpectedly matched Token('a')")
            case Token('A'):
                pass
            case _:
                self.fail("Token did not match the expected Token('A') pattern")

    def test_matches_with_token_kwarg_type(self):
        match self.token:
            case Token(type='A'):
                pass
            case _:
                self.fail("Token did not match the expected type 'A'")

    def test_matches_with_bad_token_type(self):
        match self.token:
            case Token(type='B'):
                self.fail("Token unexpectedly matched type 'B'")
            case _:
                pass

    def test_match_on_tree(self):
        # Give each Tree its children as a list.
        tree1 = Tree('a', [Tree(x, [y]) for x, y in zip('bcd', 'xyz')])

        tree2 = Tree('a', [
            Tree('b', [Token('T', 'x')]),
            Tree('c', [Token('T', 'y')]),
            Tree('d', [
                Tree('z', [
                    Token('T', 'zz'),
                    Tree('zzz', ['zzz'])
                ])
            ]),
        ])

        # Check patterns that should not match tree1.
        match tree1:
            case Tree('X', []):
                self.fail("tree1 unexpectedly matched Tree('X', [])")
            case Tree('a', []):
                self.fail("tree1 unexpectedly matched an empty tree")
            case Tree('X', _):
                self.fail("tree1 unexpectedly matched a tree named 'X'")
            case Tree('a', [Tree('b', _), *remaining]):
                # Match the first child named 'b'.
                # Collect the other children in remaining.
                self.assertEqual(
                    [child.data for child in remaining],
                    ['c', 'd']
                )
            case _:
                self.fail("tree1 did not match the expected structure")

        tree = Tree('q', [Token('T', 'x')])
        match tree:
            case Tree('q', [Token('T', 'x')]):
                pass
            case _:
                self.fail("tree did not match its expected structure")

        tr = Tree('a', [Tree('b', [Token('T', 'a')])])
        match tr:
            case Tree('a', [Tree('b', [Token('T', 'a')])]):
                pass
            case _:
                self.fail("nested tree did not match its expected structure")

        # Test nested trees.
        match tree2:
            case Tree('a', [
                Tree('b', [Token('T', 'x')]),
                Tree('c', [Token('T', 'y')]),
                Tree('d', [
                    Tree('z', [
                        Token('T', 'zz'),
                        Tree('zzz', ['zzz'])
                    ])
                ])
            ]):
                pass
            case _:
                self.fail("tree2 did not match its expected nested structure")


if __name__ == '__main__':
    main()
