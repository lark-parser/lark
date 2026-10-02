from __future__ import absolute_import

from unittest import TestCase

from lark.utils import TextSlice


class TestTextSlice(TestCase):
    def test_end_past_the_text(self):
        self.assertRaises(AssertionError, TextSlice, "hello", 0, 100)

    def test_negative_end_past_the_text(self):
        self.assertRaises(AssertionError, TextSlice, "hello", 0, -100)

    def test_start_past_the_text(self):
        self.assertRaises(AssertionError, TextSlice, "hello", 10, 12)

    def test_negative_end_inside_the_text(self):
        view = TextSlice("hello", 1, -1)
        self.assertEqual((view.start, view.end, len(view)), (1, 4, 3))
