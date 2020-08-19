from copy import deepcopy
from unittest import TestCase, main
from lark import Lark
from lark.tree_validator import TreeValidator
from lark import Lark

def _swap_children(t, a, b):
    t.children[a], t.children[b] = t.children[b], t.children[a]

class TestValidator(TestCase):
    def test_templates_and_inlined(self):
        p = Lark("""
        start: heading paragraph{text} heading paragraph{_p1} _p1

        _p1: text emph

        heading: text?
        paragraph{elem}: elem
        emph: text

        text:
        """)  # , ambiguity='explicit')
        tv = TreeValidator(p)

        good_tree = p.parse('')
        assert tv.validate(good_tree)

        # Swap 1 and 3, which are same template with different args
        bad_tree = deepcopy(good_tree)
        _swap_children(bad_tree, 1, 3)
        assert not tv.validate(bad_tree)

    def test_list(self):
        p = Lark(r"""start: list
                    list: | item "," list
                    item : A
                    A: "a"
                    """)
        tv = TreeValidator(p)

        r = p.parse('')
        assert tv.validate(r)

        r = p.parse("a,")
        assert tv.validate(r)

        r = p.parse("a,a,")
        assert tv.validate(r)

        r.data = "bad_start"
        assert not tv.validate(r)


if __name__ == '__main__':
    main()