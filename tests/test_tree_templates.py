from __future__ import absolute_import

import unittest
from copy import deepcopy

from lark import Lark, Tree, Token
from lark.exceptions import MissingVariableError
from lark.tree_templates import TemplateConf, Template, TemplateTranslator

SOME_NON_TEMPLATED_STRING = "foo bar"
SOME_TEMPLATE_NAME = "thing"
SOME_TEMPLATE_STRING = f"${SOME_TEMPLATE_NAME}"
SOME_NON_STRING = 12345
SOME_TEMPLATING_GRAMMAR = r"""
start: DASHES? foo DASHES? bar
DASHES: "--"
foo: "foo"
    | TEMPLATE_NAME -> var
bar: "bar"
    | TEMPLATE_NAME -> var
TEMPLATE_NAME: "$" NAME
NAME: /[^\W\d]\w*/
%ignore /[\t \f]+/  // WS
"""
SOME_FOO_TEMPLATE = f"{SOME_TEMPLATE_STRING} bar"
SOME_BAR_TEMPLATE = f"foo {SOME_TEMPLATE_STRING}"
SOME_NON_TEMPLATE_TREE = Tree("foo", children=["hi"])

__all__ = [
    "TestTreeTemplatesConf",
    "TestTreeTemplatesTemplateTranslator",
    "TestTreeTemplatesTemplate",
    "TestTreeTemplatesTemplateDefaultConf",
]


class TestTreeTemplatesConf(unittest.TestCase):
    parser = Lark(SOME_TEMPLATING_GRAMMAR)

    def test_conf_test_var__not_var(self):
        conf = TemplateConf(self.parser.parse)

        non_templates = {
            "non-templated string": SOME_NON_TEMPLATED_STRING,
            "non-var tree": Tree("stmt", children=[]),
            "var tree, non-templated string": Tree(
                "var", children=[SOME_NON_TEMPLATED_STRING]
            ),
            "var tree, templated string not first child": Tree(
                "var", children=[SOME_NON_TEMPLATED_STRING, SOME_TEMPLATE_STRING]
            ),
            "var tree, first child not string": Tree("var", children=[SOME_NON_STRING]),
            "var tree, no children": Tree("var", children=[]),
        }
        for description, test_case in non_templates.items():
            with self.subTest(msg=description):
                self.assertIsNone(conf.test_var(test_case))

    def test_conf_test_var__is_var(self):
        conf = TemplateConf(self.parser.parse)

        non_templates = {
            "templated string": SOME_TEMPLATE_STRING,
            "var tree, non-templated string": Tree(
                "var", children=[SOME_TEMPLATE_STRING]
            ),
        }
        for description, test_case in non_templates.items():
            with self.subTest(msg=description):
                self.assertEqual(SOME_TEMPLATE_NAME, conf.test_var(test_case))

    def test_conf_call__same_tree(self):
        conf = TemplateConf(self.parser.parse)
        explicitly_parsed = self.parser.parse(SOME_FOO_TEMPLATE)

        non_templates = {
            "to be parsed": SOME_FOO_TEMPLATE,
            "already parsed": explicitly_parsed,
        }
        for description, test_case in non_templates.items():
            with self.subTest(msg=description):
                template = conf(test_case)
                self.assertEqual(explicitly_parsed, template.tree)

    def test_template_match__default_conf_match_same_tree__empty_dictionary(self):
        template = Template(SOME_NON_TEMPLATE_TREE)

        self.assertEqual({}, template.match(SOME_NON_TEMPLATE_TREE))

    def test_template_match__only_tree(self):
        "This test might become irrelevant in the future"
        template_tree = Tree('bar', [Tree("var", children=["$foo"])])
        template = Template(template_tree)
        self.assertRaises(TypeError, template.match, Tree('bar', ['BAD']))


class TestTreeTemplatesTemplate(unittest.TestCase):
    parser = Lark(SOME_TEMPLATING_GRAMMAR)
    conf = TemplateConf(parser.parse)

    def test_template_match__same_tree_no_template__empty_dictionary(self):
        template = Template(SOME_NON_TEMPLATE_TREE, conf=self.conf)

        self.assertEqual({}, template.match(SOME_NON_TEMPLATE_TREE))

    def test_template_match__different_tree_no_template__none(self):
        template = Template(SOME_NON_TEMPLATE_TREE, conf=self.conf)

        self.assertIsNone(template.match(Tree("foo", children=["bye"])))

    def test_template_match__no_template__empty_dictionary(self):
        tree = self.parser.parse(SOME_NON_TEMPLATED_STRING)
        template = Template(tree, conf=self.conf)

        non_templates = {
            "un-parsed string": SOME_NON_TEMPLATED_STRING,
            "parsed tree": tree,
        }
        for description, test_case in non_templates.items():
            with self.subTest(msg=description):
                self.assertEqual({}, template.match(test_case))

    def test_template_match__with_template__empty_dictionary(self):
        tree = self.parser.parse(SOME_FOO_TEMPLATE)
        template = Template(tree, conf=self.conf)

        non_templates = {"un-parsed string": SOME_FOO_TEMPLATE, "parsed tree": tree}
        expected_result = {SOME_TEMPLATE_NAME: tree.children[0]}

        for description, test_case in non_templates.items():
            with self.subTest(msg=description):
                self.assertEqual(expected_result, template.match(test_case))

    def test_template_match__different_tree__none(self):
        tree = self.parser.parse(SOME_FOO_TEMPLATE)
        template = Template(tree, conf=self.conf)

        non_templates = {
            "un-parsed string": SOME_BAR_TEMPLATE,
            "parsed tree": self.parser.parse(SOME_BAR_TEMPLATE),
        }
        for description, test_case in non_templates.items():
            with self.subTest(msg=description):
                self.assertIsNone(template.match(test_case))

    def test_template_search__same_tree_no_template__empty_generator(self):
        template = Template(SOME_NON_TEMPLATE_TREE, conf=self.conf)

        self.assertEqual([], list(template.search(SOME_NON_TEMPLATE_TREE)))

    def test_template_search__same_tree_as_child__empty_generator(self):
        template = Template(SOME_NON_TEMPLATE_TREE, conf=self.conf)

        self.assertEqual(
            [], list(template.search(Tree("root", children=[SOME_NON_TEMPLATE_TREE])))
        )

    def test_template_search__with_template__matched_result_with_parent_tree(self):
        tree = self.parser.parse(SOME_FOO_TEMPLATE)
        template = Template(tree, conf=self.conf)

        non_templates = {"un-parsed string": SOME_FOO_TEMPLATE, "parsed tree": tree}
        expected_result = [(tree, {SOME_TEMPLATE_NAME: tree.children[0]})]

        for description, test_case in non_templates.items():
            with self.subTest(msg=description):
                self.assertEqual(expected_result, list(template.search(test_case)))

    def test_template_apply_vars__empty__exception(self):
        tree = self.parser.parse(SOME_FOO_TEMPLATE)
        template = Template(tree, conf=self.conf)

        with self.assertRaises(MissingVariableError):
            template.apply_vars({})

    def test_template_apply_vars__no_matching_vars__exception(self):
        tree = self.parser.parse(SOME_FOO_TEMPLATE)
        template = Template(tree, conf=self.conf)

        with self.assertRaises(MissingVariableError):
            template.apply_vars({"not used": SOME_NON_TEMPLATE_TREE})

    def test_template_apply_vars__matching_vars__template_replaced(self):
        tree = self.parser.parse(SOME_FOO_TEMPLATE)
        template = Template(tree, conf=self.conf)

        expected_result = deepcopy(tree)
        expected_result.children[0] = SOME_NON_TEMPLATE_TREE
        self.assertEqual(
            expected_result,
            template.apply_vars({SOME_TEMPLATE_NAME: SOME_NON_TEMPLATE_TREE}),
        )


class TestTreeTemplatesTemplateTranslator(unittest.TestCase):
    parser = Lark(SOME_TEMPLATING_GRAMMAR)
    conf = TemplateConf(parser.parse)

    def test_translate__empty_translations__same_tree(self):
        # no translations to match, so doesn't replace anything & can't error
        translator = TemplateTranslator({})
        tree = self.parser.parse(SOME_FOO_TEMPLATE)

        expected_result = deepcopy(tree)
        self.assertEqual(expected_result, translator.translate(tree))

    def test_translate__one_translations__same_tree(self):
        translations = {
            self.conf(f"${SOME_TEMPLATE_NAME} bar"): self.conf(
                f"--${SOME_TEMPLATE_NAME}-- bar"
            )
        }
        translator = TemplateTranslator(translations)
        tree = self.parser.parse(SOME_NON_TEMPLATED_STRING)

        expected_result = deepcopy(tree)
        expected_result.children.insert(0, Token("DASHES", "--"))
        expected_result.children.insert(2, Token("DASHES", "--"))
        self.assertEqual(expected_result, translator.translate(tree))


class TestTreeTemplatesTemplateDefaultConf(unittest.TestCase):
    def test_template_match__match_same_tree__empty_dictionary(self):
        tree = Tree("foo", children=["hi"])
        template = Template(tree)

        self.assertEqual({}, template.match(tree))


if __name__ == "__main__":
    unittest.main()
