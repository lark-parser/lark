from __future__ import absolute_import

from unittest import TestCase
import logging
import copy
import pickle

from lark.tree import Tree


class TestTrees(TestCase):
    def setUp(self):
        self.tree1 = Tree('a', [Tree(x, y) for x, y in zip('bcd', 'xyz')])

    def test_deepcopy(self):
        assert self.tree1 == copy.deepcopy(self.tree1)

    def test_pickle(self):
        s = copy.deepcopy(self.tree1)
        data = pickle.dumps(s)
        assert pickle.loads(data) == s


if __name__ == '__main__':
    unittest.main()

