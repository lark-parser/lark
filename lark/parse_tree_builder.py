from .common import is_terminal, GrammarError
from .lexer import Token

class Callback(object):
    pass


def create_expand1_tree_builder_function(tree_builder):
    def expand1(children):
        if len(children) == 1:
            return children[0]
        else:
            return tree_builder(children)
    return expand1

def create_token_wrapper(tree_builder, name):
    def join_children(children):
        children = [Token(name, ''.join(children))]
        return tree_builder(children)
    return join_children

def create_rule_handler(expansion, usermethod, keep_all_tokens, filter_out):
    # if not keep_all_tokens:
    to_include = [(i, not is_terminal(sym) and sym.startswith('_'))
                  for i, sym in enumerate(expansion)
                  if keep_all_tokens
                  or not ((is_terminal(sym) and sym.startswith('_')) or sym in filter_out)
                  ]

    if len(to_include) < len(expansion) or any(to_expand for i, to_expand in to_include):
        def _build_ast(match):
            children = []
            for i, to_expand in to_include:
                if to_expand:
                    children += match[i].children
                else:
                    children.append(match[i])

            return usermethod(children)
        return _build_ast

    # else, if no filtering required..
    return usermethod


class ParseTreeBuilder:
    def __init__(self, tree_class):
        self.tree_class = tree_class

    def _create_tree_builder_function(self, name):
        tree_class = self.tree_class
        def tree_builder_f(children):
            return tree_class(name, children)
        return tree_builder_f



    def create_tree_builder(self, rules, transformer):
        callback = Callback()
        new_rules = []

        filter_out = set()
        for origin, (expansions, options) in rules.items():
            if options and options.filter_out:
                assert origin.startswith('_')   # Just to make sure
                filter_out.add(origin)

        for origin, (expansions, options) in rules.items():
            keep_all_tokens = options.keep_all_tokens if options else False
            expand1 = options.expand1 if options else False
            create_token = options.create_token if options else False

            _origin = origin

            for expansion, alias in expansions:
                if alias and origin.startswith('_'):
                    raise Exception("Rule %s is marked for expansion (it starts with an underscore) and isn't allowed to have aliases (alias=%s)" % (origin, alias))

                try:
                    f = transformer._get_func(alias or _origin)
                except AttributeError:
                    if alias:
                        f = self._create_tree_builder_function(alias)
                    else:
                        f = self._create_tree_builder_function(_origin)
                        if expand1:
                            f = create_expand1_tree_builder_function(f)

                    if create_token:
                        f = create_token_wrapper(f, create_token)


                alias_handler = create_rule_handler(expansion, f, keep_all_tokens, filter_out)

                callback_name = 'autoalias_%s_%s' % (_origin, '_'.join(expansion))
                if hasattr(callback, callback_name):
                    raise GrammarError("Rule expansion '%s' already exists in rule %s" % (' '.join(expansion), origin))
                setattr(callback, callback_name, alias_handler)

                new_rules.append(( _origin, expansion, callback_name ))

        return new_rules, callback
