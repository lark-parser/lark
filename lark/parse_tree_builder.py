from .common import is_terminal

class Callback(object):
    pass


def create_expand1_tree_builder_function(tree_builder):
    def f(children):
        if len(children) == 1:
            return children[0]
        else:
            return tree_builder(children)
    return f

def create_rule_handler(expansion, usermethod):
    to_include = [(i, sym.startswith('_')) for i, sym in enumerate(expansion)
                  if not (is_terminal(sym) and sym.startswith('_'))]

    if len(to_include) < len(expansion) or any(to_expand for i, to_expand in to_include):
        def _build_ast(match):
            children = []
            for i, to_expand in to_include:
                if to_expand:
                    children += match[i].children
                else:
                    children.append(match[i])

            return usermethod(children)
    else:
        _build_ast = usermethod

    return _build_ast


class ParseTreeBuilder:
    def __init__(self, tree_class):
        self.tree_class = tree_class

    def _create_tree_builder_function(self, name):
        tree_class = self.tree_class
        def f(children):
            return tree_class(name, children)
        return f


    def create_tree_builder(self, rules, transformer):
        callback = Callback()
        new_rules = []
        for origin, expansions in rules.items():
            expand1 = origin.startswith('?')
            _origin = origin.lstrip('?*')

            for expansion, alias in expansions:
                if alias and origin.startswith('_'):
                    raise Exception("Rule %s is marked for expansion (it starts with an underscore) and isn't allowed to have aliases" % origin)

                if alias:
                    alias = alias.lstrip('*')
                _alias = 'autoalias_%s_%s' % (_origin, '_'.join(expansion))

                try:
                    f = transformer._get_func(alias or _origin)
                except AttributeError:
                    if alias:
                        f = self._create_tree_builder_function(alias)
                    else:
                        f = self._create_tree_builder_function(_origin)
                        if expand1:
                            f = create_expand1_tree_builder_function(f)

                alias_handler = create_rule_handler(expansion, f)

                assert not hasattr(callback, _alias)
                setattr(callback, _alias, alias_handler)

                new_rules.append(( _origin, expansion, _alias ))

        return new_rules, callback


