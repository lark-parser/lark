from .exceptions import GrammarError
from .lexer import Token
from .tree import Tree
from .visitors import InlineTransformer # XXX Deprecated
from .visitors import Transformer_InPlace
from .visitors import _vargs_meta, _vargs_meta_inline

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

        # local reference to Tree.meta reduces number of presence checks
        if isinstance(res, Tree):
            res_meta = res.meta
            for c in children:
                if isinstance(c, Tree):
                    child_meta = c.meta
                    if not child_meta.empty:
                        res_meta.line = child_meta.line
                        res_meta.column = child_meta.column
                        res_meta.start_pos = child_meta.start_pos
                        res_meta.empty = False
                        break
                elif isinstance(c, Token):
                    res_meta.line = c.line
                    res_meta.column = c.column
                    res_meta.start_pos = c.pos_in_stream
                    res_meta.empty = False
                    break

            for c in reversed(children):
                if isinstance(c, Tree):
                    child_meta = c.meta
                    if not child_meta.empty:
                        res_meta.end_line = child_meta.end_line
                        res_meta.end_column = child_meta.end_column
                        res_meta.end_pos = child_meta.end_pos
                        res_meta.empty = False
                        break
                elif isinstance(c, Token):
                    res_meta.end_line = c.end_line
                    res_meta.end_column = c.end_column
                    res_meta.end_pos = c.end_pos
                    res_meta.empty = False
                    break

        return res


class ChildFilter:
    def __init__(self, to_include, append_none, node_builder):
        self.node_builder = node_builder
        self.to_include = to_include
        self.append_none = append_none

    def __call__(self, children):
        filtered = []

        for i, to_expand, add_none in self.to_include:
            if add_none:
                filtered += [None] * add_none
            if to_expand:
                filtered += children[i].children
            else:
                filtered.append(children[i])

        if self.append_none:
            filtered += [None] * self.append_none

        return self.node_builder(filtered)

class ChildFilterLALR(ChildFilter):
    "Optimized childfilter for LALR (assumes no duplication in parse tree, so it's safe to change it)"

    def __call__(self, children):
        filtered = []
        for i, to_expand, add_none in self.to_include:
            if add_none:
                filtered += [None] * add_none
            if to_expand:
                if filtered:
                    filtered += children[i].children
                else:   # Optimize for left-recursion
                    filtered = children[i].children
            else:
                filtered.append(children[i])

        if self.append_none:
            filtered += [None] * self.append_none

        return self.node_builder(filtered)

class ChildFilterLALR_NoPlaceholders(ChildFilter):
    "Optimized childfilter for LALR (assumes no duplication in parse tree, so it's safe to change it)"
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

def maybe_create_child_filter(expansion, keep_all_tokens, ambiguous, _empty_indices):
    # Prepare empty_indices as: How many Nones to insert at each index?
    if _empty_indices:
        assert _empty_indices.count(False) == len(expansion)
        s = ''.join(str(int(b)) for b in _empty_indices)
        empty_indices = [len(ones) for ones in s.split('0')]
        assert len(empty_indices) == len(expansion)+1, (empty_indices, len(expansion))
    else:
        empty_indices = [0] * (len(expansion)+1)

    to_include = []
    nones_to_add = 0
    for i, sym in enumerate(expansion):
        nones_to_add += empty_indices[i]
        if keep_all_tokens or not (sym.is_term and sym.filter_out):
            to_include.append((i, _should_expand(sym), nones_to_add))
            nones_to_add = 0

    nones_to_add += empty_indices[len(expansion)]

    if _empty_indices or len(to_include) < len(expansion) or any(to_expand for i, to_expand,_ in to_include):
        if _empty_indices or ambiguous:
            return partial(ChildFilter if ambiguous else ChildFilterLALR, to_include, nones_to_add)
        else:
            # LALR without placeholders
            return partial(ChildFilterLALR_NoPlaceholders, [(i, x) for i,x,_ in to_include])

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

        #### When we're repeatedly expanding ambiguities we can end up with nested ambiguities.
        #    All children of an _ambig node should be a derivation of that ambig node, hence
        #    it is safe to assume that if we see an _ambig node nested within an ambig node
        #    it is safe to simply expand it into the parent _ambig node as an alternative derivation.
        ambiguous = []
        for i, child in enumerate(children):
            if _is_ambig_tree(child):
                if i in self.to_expand:
                    ambiguous.append(i)

                to_expand = [j for j, grandchild in enumerate(child.children) if _is_ambig_tree(grandchild)]
                child.expand_kids_by_index(*to_expand)

        if not ambiguous:
            return self.node_builder(children)

        expand = [ iter(child.children) if i in ambiguous else repeat(child) for i, child in enumerate(children) ]
        return self.tree_class('_ambig', [self.node_builder(list(f[0])) for f in product(zip(*expand))])

def maybe_create_ambiguous_expander(tree_class, expansion, keep_all_tokens):
    to_expand = [i for i, sym in enumerate(expansion)
                 if keep_all_tokens or ((not (sym.is_term and sym.filter_out)) and _should_expand(sym))]
    if to_expand:
        return partial(AmbiguousExpander, to_expand, tree_class)

def ptb_inline_args(func):
    @wraps(func)
    def f(children):
        return func(*children)
    return f

def inplace_transformer(func):
    @wraps(func)
    def f(children):
        # function name in a Transformer is a rule name.
        tree = Tree(func.__name__, children)
        return func(tree)
    return f

def apply_visit_wrapper(func, name, wrapper):
    if wrapper is _vargs_meta or wrapper is _vargs_meta_inline:
        raise NotImplementedError("Meta args not supported for internal transformer")
    @wraps(func)
    def f(children):
        return wrapper(func, name, children, None)
    return f


class ParseTreeBuilder:
    def __init__(self, rules, tree_class, propagate_positions=False, keep_all_tokens=False, ambiguous=False, maybe_placeholders=False):
        self.tree_class = tree_class
        self.propagate_positions = propagate_positions
        self.always_keep_all_tokens = keep_all_tokens
        self.ambiguous = ambiguous
        self.maybe_placeholders = maybe_placeholders

        self.rule_builders = list(self._init_builders(rules))

    def _init_builders(self, rules):
        for rule in rules:
            options = rule.options
            keep_all_tokens = self.always_keep_all_tokens or options.keep_all_tokens
            expand_single_child = options.expand1

            wrapper_chain = list(filter(None, [
                (expand_single_child and not rule.alias) and ExpandSingleChild,
                maybe_create_child_filter(rule.expansion, keep_all_tokens, self.ambiguous, options.empty_indices if self.maybe_placeholders else None),
                self.propagate_positions and PropagatePositions,
                self.ambiguous and maybe_create_ambiguous_expander(self.tree_class, rule.expansion, keep_all_tokens),
            ]))

            yield rule, wrapper_chain


    def create_callback(self, transformer=None):
        callbacks = {}

        for rule, wrapper_chain in self.rule_builders:

            user_callback_name = rule.alias or rule.options.template_source or rule.origin.name
            try:
                f = getattr(transformer, user_callback_name)
                # XXX InlineTransformer is deprecated!
                wrapper = getattr(f, 'visit_wrapper', None)
                if wrapper is not None:
                    f = apply_visit_wrapper(f, user_callback_name, wrapper)
                else:
                    if isinstance(transformer, InlineTransformer):
                        f = ptb_inline_args(f)
                    elif isinstance(transformer, Transformer_InPlace):
                        f = inplace_transformer(f)
            except AttributeError:
                f = partial(self.tree_class, user_callback_name)

            for w in wrapper_chain:
                f = w(f)

            if rule in callbacks:
                raise GrammarError("Rule '%s' already exists" % (rule,))

            callbacks[rule] = f

        return callbacks

###}
