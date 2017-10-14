from .common import is_terminal, GrammarError
from .utils import suppress
from .lexer import Token

class NodeBuilder:
    def __init__(self, tree_class, name):
        self.tree_class = tree_class
        self.name = name

    def __call__(self, children):
        return self.tree_class(self.name, children)

class Expand1:
    def __init__(self, node_builder):
        self.node_builder = node_builder

    def __call__(self, children):
        if len(children) == 1:
            return children[0]
        else:
            return self.node_builder(children)

class TokenWrapper:
    "Used for fixing the results of scanless parsing"

    def __init__(self, node_builder, token_name):
        self.node_builder = node_builder
        self.token_name = token_name

    def __call__(self, children):
        return self.node_builder( [Token(self.token_name, ''.join(children))] )

class ChildFilter:
    def __init__(self, node_builder, to_include):
        self.node_builder = node_builder
        self.to_include = to_include

    def __call__(self, children):
        filtered = []
        for i, to_expand in self.to_include:
            if to_expand:
                filtered += children[i].children
            else:
                filtered.append(children[i])

        return self.node_builder(filtered)

def create_rule_handler(expansion, usermethod, keep_all_tokens, filter_out):
    # if not keep_all_tokens:
    to_include = [(i, not is_terminal(sym) and sym.startswith('_'))
                  for i, sym in enumerate(expansion)
                  if keep_all_tokens
                  or not ((is_terminal(sym) and sym.startswith('_')) or sym in filter_out)
                  ]

    if len(to_include) < len(expansion) or any(to_expand for i, to_expand in to_include):
        return ChildFilter(usermethod, to_include)

    # else, if no filtering required..
    return usermethod

class PropagatePositions:
    def __init__(self, node_builder):
        self.node_builder = node_builder

    def __call__(self, children):
        res = self.node_builder(children)

        if children:
            for a in children:
                with suppress(AttributeError):
                    res.line = a.line
                    res.column = a.column
                break

            for a in reversed(children):
                with suppress(AttributeError):
                    res.end_line = a.end_line
                    res.end_col = a.end_col
                break

        return res


class Callback(object):
    pass

class ParseTreeBuilder:
    def __init__(self, tree_class, propagate_positions=False, keep_all_tokens=False):
        self.tree_class = tree_class
        self.propagate_positions = propagate_positions
        self.always_keep_all_tokens = keep_all_tokens

    def create_tree_builder(self, rules, transformer):
        callback = Callback()
        new_rules = []

        filter_out = set()
        for origin, (expansions, options) in rules.items():
            if options and options.filter_out:
                assert origin.startswith('_')   # Just to make sure
                filter_out.add(origin)

        for origin, (expansions, options) in rules.items():
            keep_all_tokens = self.always_keep_all_tokens or (options.keep_all_tokens if options else False)
            expand1 = options.expand1 if options else False
            create_token = options.create_token if options else False

            for expansion, alias in expansions:
                if alias and origin.startswith('_'):
                        raise Exception("Rule %s is marked for expansion (it starts with an underscore) and isn't allowed to have aliases (alias=%s)" % (origin, alias))

                elif not alias:
                    alias = origin

                try:
                    f = transformer._get_func(alias)
                except AttributeError:
                    f = NodeBuilder(self.tree_class, alias)

                if expand1:
                    f = Expand1(f)

                if create_token:
                    f = TokenWrapper(f, create_token)

                alias_handler = create_rule_handler(expansion, f, keep_all_tokens, filter_out)

                if self.propagate_positions:
                    alias_handler = PropagatePositions(alias_handler)

                callback_name = 'autoalias_%s_%s' % (origin, '_'.join(expansion))
                if hasattr(callback, callback_name):
                    raise GrammarError("Rule expansion '%s' already exists in rule %s" % (' '.join(expansion), origin))
                setattr(callback, callback_name, alias_handler)

                new_rules.append(( origin, expansion, callback_name, options ))

        return new_rules, callback
