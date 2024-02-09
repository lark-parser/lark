from .lexer import Token
from .load_grammar import GrammarError
from .visitors import Visitor
from .tree import Tree

class LarkValidatorVisitor(Visitor):

    @classmethod
    def validate(cls, tree: Tree):
        visitor = cls()
        visitor.visit(tree)
        return tree

    def alias(self, tree: Tree):
        # Reject alias names in inner 'expansions'.
        self._reject_aliases(tree.children[0], "Deep aliasing not allowed")

    def ignore(self, tree: Tree):
        # Reject everything except 'literal' and 'name' > 'TOKEN'.
        assert len(tree.children) > 0    # The grammar should pass us some things to ignore.
        if len(tree.children) > 1:
            self._reject_bad_ignore()
        node = tree.children[0]
        if node.data == "expansions":
            if len(node.children) > 1:
                self._reject_bad_ignore()
            node = node.children[0]
        if node.data == "alias":
            if len(node.children) > 1:
                self._reject_bad_ignore()
            node = node.children[0]
        if node.data == "expansion":
            if len(node.children) > 1:
                self._reject_bad_ignore()
            node = node.children[0]
        if node.data == "expr":
            if len(node.children) > 1:
                self._reject_bad_ignore()
            node = node.children[0]
        if node.data == "atom":
            if len(node.children) > 1:
                self._reject_bad_ignore()
            node = node.children[0]
        if node.data == "literal":
            return
        elif node.data == "name":
            if node.children[0].data == "TOKEN":
                return
        elif node.data == "value":
            if node.children[0].data == "literal":
                return
            elif node.children[0].data == "name":
                if node.children[0][0].data == "TOKEN":
                    return
        self._reject_bad_ignore()

    def token(self, tree: Tree):
        assert len(tree.children) > 1    # The grammar should pass us at least a token name and an item.
        first_item = 2 if tree.children[1].data == "priority" else 1
        # Reject alias names in token definitions.
        for child in tree.children[first_item:]:
            self._reject_aliases(child, "Aliasing not allowed in terminals (You used -> in the wrong place)")
        # Reject template usage in token definitions.  We do this before checking rules
        # because rule usage looks like template usage, just without parameters.
        for child in tree.children[first_item:]:
            self._reject_templates(child, "Templates not allowed in terminals")
        # Reject rule references in token definitions.
        for child in tree.children[first_item:]:
            self._reject_rules(child, "Rules aren't allowed inside terminals")

    def _reject_aliases(self, item: Tree|Token, message: str):
        if isinstance(item, Tree):
            if item.data == "alias" and len(item.children) > 1 and item.children[1] is not None:
                raise GrammarError(message)
            for child in item.children:
                self._reject_aliases(child, message)

    def _reject_bad_ignore(self):
        raise GrammarError("Bad %ignore - must have a Terminal or other value.")

    def _reject_rules(self, item: Tree|Token, message: str):
        if isinstance(item, Token) and item.type == "RULE":
            raise GrammarError(message)
        elif isinstance(item, Tree):
            for child in item.children:
                self._reject_rules(child, message)

    def _reject_templates(self, item: Tree|Token, message: str):
        if isinstance(item, Tree):
            if item.data == "template_usage":
                raise GrammarError(message)
            for child in item.children:
                self._reject_templates(child, message)
