from .common import is_terminal, GrammarError
from .utils import suppress
from .lexer import Token
from .grammar import Rule

###{standalone

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

class Factory:
    def __init__(self, cls, *args):
        self.cls = cls
        self.args = args

    def __call__(self, node_builder):
        return self.cls(node_builder, *self.args)


class TokenWrapper:
    "Used for fixing the results of scanless parsing"

    def __init__(self, node_builder, token_name):
        self.node_builder = node_builder
        self.token_name = token_name

    def __call__(self, children):
        return self.node_builder( [Token(self.token_name, ''.join(children))] )

def identity(node_builder):
    return node_builder


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

def create_rule_handler(expansion, keep_all_tokens, filter_out):
    # if not keep_all_tokens:
    to_include = [(i, not is_terminal(sym) and sym.startswith('_'))
                  for i, sym in enumerate(expansion)
                  if keep_all_tokens
                  or not ((is_terminal(sym) and sym.startswith('_')) or sym in filter_out)
                  ]

    if len(to_include) < len(expansion) or any(to_expand for i, to_expand in to_include):
        return Factory(ChildFilter, to_include)

    # else, if no filtering required..
    return identity

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
    def __init__(self, rules, tree_class, propagate_positions=False, keep_all_tokens=False):
        self.tree_class = tree_class
        self.propagate_positions = propagate_positions
        self.always_keep_all_tokens = keep_all_tokens

        self.rule_builders = list(self._init_builders(rules))

        self.user_aliases = {}

    def _init_builders(self, rules):
        filter_out = set()
        for rule in rules:
            if rule.options and rule.options.filter_out:
                assert rule.origin.startswith('_')   # Just to make sure
                filter_out.add(rule.origin)

        for rule in rules:
            options = rule.options
            keep_all_tokens = self.always_keep_all_tokens or (options.keep_all_tokens if options else False)
            expand1 = options.expand1 if options else False
            create_token = options.create_token if options else False

            wrapper_chain = filter(None, [
                (expand1 and not rule.alias) and Expand1,
                create_token and Factory(TokenWrapper, create_token),
                create_rule_handler(rule.expansion, keep_all_tokens, filter_out),
                self.propagate_positions and PropagatePositions,
            ])

            yield rule, wrapper_chain


    def create_callback(self, transformer=None):
        callback = Callback()

        for rule, wrapper_chain in self.rule_builders:
            internal_callback_name = '_callback_%s_%s' % (rule.origin, '_'.join(rule.expansion))

            user_callback_name = rule.alias or rule.origin
            try:
                f = transformer._get_func(user_callback_name)
            except AttributeError:
                f = NodeBuilder(self.tree_class, user_callback_name)

            self.user_aliases[rule] = rule.alias
            rule.alias = internal_callback_name

            for w in wrapper_chain:
                f = w(f)

            if hasattr(callback, internal_callback_name):
                raise GrammarError("Rule '%s' already exists" % (rule,))
            setattr(callback, internal_callback_name, f)

        return callback

###}
