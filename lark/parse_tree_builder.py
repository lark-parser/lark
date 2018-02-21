from .common import is_terminal, GrammarError
from .utils import suppress
from .lexer import Token
from .grammar import Rule
from itertools import repeat, product

###{standalone
from functools import partial


class ExpandSingleChild:
    def __init__(self, node_builder):
        self.node_builder = node_builder

    def __call__(self, children):
        if len(children) == 1:
            return children[0]
        else:
            return self.node_builder(children)


class CreateToken:
    "Used for fixing the results of scanless parsing"

    def __init__(self, token_name, node_builder):
        self.node_builder = node_builder
        self.token_name = token_name

    def __call__(self, children):
        return self.node_builder( [Token(self.token_name, ''.join(children))] )


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
                    res.end_column = a.end_column
                break

        return res


class ChildFilter:
    def __init__(self, to_include, node_builder):
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

class ChildFilterLALR(ChildFilter):
    "Optimized childfilter for LALR (assumes no duplication in parse tree, so it's safe to change it)"

    def __call__(self, children):
        filtered = []
        for i, to_expand in self.to_include:
            if to_expand:
                if filtered:
                    filtered += children[i].children
                else:   # Optimize for left-recursion
                    filtered = children[i].children
            else:
                filtered.append(children[i])

        return self.node_builder(filtered)

def _should_expand(sym):
    return not is_terminal(sym) and sym.startswith('_')

def maybe_create_child_filter(expansion, filter_out, ambiguous):
    to_include = [(i, _should_expand(sym)) for i, sym in enumerate(expansion) if sym not in filter_out]

    if len(to_include) < len(expansion) or any(to_expand for i, to_expand in to_include):
        return partial(ChildFilter if ambiguous else ChildFilterLALR, to_include)

class AmbiguousExpander:
    def __init__(self, to_expand, tree_class, node_builder):
        self.node_builder = node_builder
        self.tree_class = tree_class
        self.to_expand = to_expand

    def __call__(self, children):
        def _is_ambig_tree(child):
            return hasattr(child, 'data') and child.data == '_ambig'

        ambiguous = [i for i in self.to_expand if _is_ambig_tree(children[i])]
        if ambiguous:
            expand = [iter(child.children) if i in ambiguous else repeat(child) for i, child in enumerate(children)]
            return self.tree_class('_ambig', [self.node_builder(list(f[0])) for f in product(zip(*expand))])
        return self.node_builder(children)

def maybe_create_ambiguous_expander(tree_class, expansion, filter_out):
    to_expand = [i for i, sym in enumerate(expansion) if sym not in filter_out and _should_expand(sym)]

    if to_expand:
        return partial(AmbiguousExpander, to_expand, tree_class)

class Callback(object):
    pass

class ParseTreeBuilder:
    def __init__(self, rules, tree_class, propagate_positions=False, keep_all_tokens=False, ambiguous=False):
        self.tree_class = tree_class
        self.propagate_positions = propagate_positions
        self.always_keep_all_tokens = keep_all_tokens
        self.ambiguous = ambiguous

        self.rule_builders = list(self._init_builders(rules))

        self.user_aliases = {}

    def _init_builders(self, rules):
        filter_out = {rule.origin for rule in rules if rule.options and rule.options.filter_out}
        filter_out |= {sym for rule in rules for sym in rule.expansion if is_terminal(sym) and sym.startswith('_')}
        assert all(x.startswith('_') for x in filter_out)

        for rule in rules:
            options = rule.options
            keep_all_tokens = self.always_keep_all_tokens or (options.keep_all_tokens if options else False)
            expand_single_child = options.expand1 if options else False
            create_token = options.create_token if options else False
            ambiguity = self.ambiguous

            wrapper_chain = filter(None, [
                create_token and partial(CreateToken, create_token),
                (expand_single_child and not rule.alias) and ExpandSingleChild,
                maybe_create_child_filter(rule.expansion, () if keep_all_tokens else filter_out, self.ambiguous),
                self.propagate_positions and PropagatePositions,
                ambiguity and maybe_create_ambiguous_expander(self.tree_class, rule.expansion, () if keep_all_tokens else filter_out),
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
                f = partial(self.tree_class, user_callback_name)

            self.user_aliases[rule] = rule.alias
            rule.alias = internal_callback_name

            for w in wrapper_chain:
                f = w(f)

            if hasattr(callback, internal_callback_name):
                raise GrammarError("Rule '%s' already exists" % (rule,))
            setattr(callback, internal_callback_name, f)

        return callback

###}
