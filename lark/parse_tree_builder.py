from .exceptions import GrammarError
from .utils import suppress
from .lexer import Token
from .grammar import Rule
from .tree import Tree
from .visitors import InlineTransformer # XXX Deprecated

###{standalone
from functools import partial, wraps
from itertools import repeat, product


class ExpandSingleChild:
    def __init__(self, node_builder):
        self.node_builder = node_builder

    def __call__(self, children):
        if len(children) == 1:
            return children[0]
        else:
            return self.node_builder(children)


class PropagatePositions:
    def __init__(self, node_builder):
        self.node_builder = node_builder

    def __call__(self, children):
        res = self.node_builder(children)

        if isinstance(res, Tree) and getattr(res.meta, 'empty', True):
            res.meta.empty = True

            for c in children:
                if isinstance(c, Tree) and c.children and not c.meta.empty:
                    res.meta.line = c.meta.line
                    res.meta.column = c.meta.column
                    res.meta.start_pos = c.meta.start_pos
                    res.meta.empty = False
                    break
                elif isinstance(c, Token):
                    res.meta.line = c.line
                    res.meta.column = c.column
                    res.meta.start_pos = c.pos_in_stream
                    res.meta.empty = False
                    break

            for c in reversed(children):
                if isinstance(c, Tree) and c.children and not c.meta.empty:
                    res.meta.end_line = c.meta.end_line
                    res.meta.end_column = c.meta.end_column
                    res.meta.end_pos = c.meta.end_pos
                    res.meta.empty = False
                    break
                elif isinstance(c, Token):
                    res.meta.end_line = c.end_line
                    res.meta.end_column = c.end_column
                    res.meta.end_pos = c.pos_in_stream + len(c.value)
                    res.meta.empty = False
                    break

        return res


class ChildFilter:
    "Optimized childfilter (assumes no duplication in parse tree, so it's safe to change it)"
    def __init__(self, to_include, node_builder):
        self.node_builder = node_builder
        self.to_include = to_include

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
    return not sym.is_term and sym.name.startswith('_')

def maybe_create_child_filter(expansion, keep_all_tokens):
    to_include = [(i, _should_expand(sym)) for i, sym in enumerate(expansion)
                  if keep_all_tokens or not (sym.is_term and sym.filter_out)]

    if len(to_include) < len(expansion) or any(to_expand for i, to_expand in to_include):
        return partial(ChildFilter, to_include)

class AmbiguousExpander:
    """Deal with the case where we're expanding children ('_rule') into a parent but the children
       are ambiguous. i.e. (parent->_ambig->_expand_this_rule). In this case, make the parent itself
       ambiguous with as many copies as their are ambiguous children, and then copy the ambiguous children
       into the right parents in the right places, essentially shifting the ambiguiuty up the tree."""
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

def maybe_create_ambiguous_expander(tree_class, expansion, keep_all_tokens):
    to_expand = [i for i, sym in enumerate(expansion)
                 if keep_all_tokens or ((not (sym.is_term and sym.filter_out)) and _should_expand(sym))]
    if to_expand:
        return partial(AmbiguousExpander, to_expand, tree_class)

class Callback(object):
    pass


def ptb_inline_args(func):
    @wraps(func)
    def f(children):
        return func(*children)
    return f

class ParseTreeBuilder:
    def __init__(self, rules, tree_class, propagate_positions=False, keep_all_tokens=False, ambiguous=False):
        self.tree_class = tree_class
        self.propagate_positions = propagate_positions
        self.always_keep_all_tokens = keep_all_tokens
        self.ambiguous = ambiguous

        self.rule_builders = list(self._init_builders(rules))

        self.user_aliases = {}

    def _init_builders(self, rules):
        for rule in rules:
            options = rule.options
            keep_all_tokens = self.always_keep_all_tokens or (options.keep_all_tokens if options else False)
            expand_single_child = options.expand1 if options else False

            wrapper_chain = filter(None, [
                (expand_single_child and not rule.alias) and ExpandSingleChild,
                maybe_create_child_filter(rule.expansion, keep_all_tokens),
                self.propagate_positions and PropagatePositions,
                self.ambiguous and maybe_create_ambiguous_expander(self.tree_class, rule.expansion, keep_all_tokens),
            ])

            yield rule, wrapper_chain


    def create_callback(self, transformer=None):
        callback = Callback()

        i = 0
        for rule, wrapper_chain in self.rule_builders:
            internal_callback_name = '_cb%d_%s' % (i, rule.origin)
            i += 1

            user_callback_name = rule.alias or rule.origin.name
            try:
                f = getattr(transformer, user_callback_name)
                assert not getattr(f, 'meta', False), "Meta args not supported for internal transformer"
                # XXX InlineTransformer is deprecated!
                if getattr(f, 'inline', False) or isinstance(transformer, InlineTransformer):
                    f = ptb_inline_args(f)
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
