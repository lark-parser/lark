"""This module defines utilities for matching and translation tree templates.

A tree templates is a tree that contains nodes that are template variables.

"""

from typing import Union, Optional, Mapping

from lark import Tree, Transformer
from lark.exceptions import MissingVariableError

TreeOrCode = Union[Tree, str]


class TemplateConf:
    """Template Configuration

    Allows customization for different uses of Template
    """

    def __init__(self, parse=None):
        self._parse = parse

    def test_var(self, var: Union[Tree, str]) -> Optional[str]:
        """Given a tree node, if it is a template variable return its name. Otherwise, return None.

        This method may be overridden for customization

        Parameters:
            var: Tree | str - The tree node to test

        """
        if isinstance(var, str) and var.startswith('$'):
            return var.lstrip('$')

        if isinstance(var, Tree) and var.data == 'var' and len(var.children) > 0:
            first_child = var.children[0]
            if isinstance(first_child, str) and first_child.startswith('$'):
                return first_child.lstrip('$')

        return None

    def _get_tree(self, template: TreeOrCode):
        if isinstance(template, str):
            assert self._parse
            template = self._parse(template)

        assert isinstance(template, Tree)
        return template

    def __call__(self, template):
        return Template(template, conf=self)

    def _match_tree_template(self, template, tree):
        template_var = self.test_var(template)
        if template_var:
            return {template_var: tree}

        if isinstance(template, str):
            if template == tree:
                return {}
            return None

        assert isinstance(template, Tree), template

        if template.data == tree.data and len(template.children) == len(tree.children):
            res = {}
            for t1, t2 in zip(template.children, tree.children):
                matches = self._match_tree_template(t1, t2)
                if matches is None:
                    return None

                res.update(matches)

            return res


class _ReplaceVars(Transformer):
    def __init__(self, conf, vars):
        self._conf = conf
        self._vars = vars

    def __default__(self, data, children, meta):
        tree = super().__default__(data, children, meta)

        var = self._conf.test_var(tree)
        if var:
            try:
                return self._vars[var]
            except KeyError:
                raise MissingVariableError(f"No mapping for template variable ({var})")
        return tree


class Template:
    """Represents a tree templates, tied to a specific configuration

    A tree template is a tree that contains nodes that are template variables.
    Those variables will match any tree.
    (future versions may support annotations on the variables, to allow more complex templates)
    """

    def __init__(self, tree: Tree, conf = TemplateConf()):
        self.conf = conf
        self.tree = conf._get_tree(tree)

    def match(self, tree: TreeOrCode):
        """Match a tree template to a tree.

        A tree template without variables will only match ``tree`` if it is equal to the template.

        Parameters:
            tree (Tree): The tree to match to the template

        Returns:
            Optional[Dict[str, Tree]]: If match is found, returns a dictionary mapping
                template variable names to their matching tree nodes.
                If no match was found, returns None.
        """
        tree = self.conf._get_tree(tree)
        return self.conf._match_tree_template(self.tree, tree)

    def search(self, tree: TreeOrCode):
        """Search for all occurances of the tree template inside ``tree``.
        """
        tree = self.conf._get_tree(tree)
        for subtree in tree.iter_subtrees():
            res = self.match(subtree)
            if res:
                yield subtree, res

    def apply_vars(self, vars: Mapping[str, Tree]):
        """Apply vars to the template tree
        """
        return _ReplaceVars(self.conf, vars).transform(self.tree)


def translate(t1: Template, t2: Template, tree: TreeOrCode):
    """Search tree and translate each occurrance of t1 into t2.
    """
    tree = t1.conf._get_tree(tree)      # ensure it's a tree, parse if necessary and possible
    for subtree, vars in t1.search(tree):
        res = t2.apply_vars(vars)
        subtree.set(res.data, res.children)
    return tree


class TemplateTranslator:
    """Utility class for translating a collection of patterns
    """

    def __init__(self, translations: Mapping[TreeOrCode, TreeOrCode]):
        assert all( isinstance(k, Template) and isinstance(v, Template) for k, v in translations.items() )
        self.translations = translations

    def translate(self, tree: Tree):
        for k, v in self.translations.items():
            tree = translate(k, v, tree)
        return tree
