from .common import is_terminal, GrammarError
from .utils import suppress
from .lexer import Token
from .grammar import Rule

###{standalone


class TreeFilter(object):
    """Base TreeFilter class.
       Each TreeFilter should have a create_if_required classmethod, that will return a 
       callable to create an instance of this filter, called while building the chain.
    """
    def __init__(self, next_filter):
        self.next_filter = next_filter

    @classmethod
    def create_if_required(cls, rule, **kwargs):
        raise NotImplemented

    def __call__(self, children):
        """Called with a list of children for each matching Tree object.
           Should optionally call up to next_filter.
           Should return a modified list of children."""
        raise NotImplemented

class Factory(object):
    def __init__(self, cls, *args):
        self.cls = cls
        self.args = args

    def __call__(self, next_filter):
        return self.cls(next_filter, *self.args)

### Always last in the chain as a fallback. Does not call further.
class NodeBuilder(TreeFilter):
    def __init__(self, next_filter, tree_class, name):
        super(NodeBuilder, self).__init__(next_filter)
        self.tree_class = tree_class
        self.name = name

    @classmethod
    def create_if_required(cls, rule, tree_class = None, name = None, **kwargs):
        name = rule.alias or rule.origin
        return Factory(cls, tree_class, name)

    def __call__(self, children):
        return self.tree_class(self.name, children)

class CallUserTransformer(TreeFilter):
    def __init__(self, next_filter, user_function):
        super(CallUserTransformer, self).__init__(node_builder)
        self.user_function = user_function

    @classmethod
    def create_if_required(cls, rule, name = None, transformer = None, **kwargs):
        user_callback_name = rule.alias or rule.origin
        try:
            user_function = transformer._get_func(user_callback_name)
        except AttributeError:
            user_function = None

        if user_function:
            return Factory(cls, user_function)

    def __call__(self, children):
        ### note: does not chain up to NodeBuilder
        return self.user_function(children)

class ExpandSingleChild(TreeFilter):
    @classmethod
    def create_if_required(cls, rule, **kwargs):
        if rule.options and rule.options.expand1: #  and not rule.alias: - could never match
            return Factory(cls)

    def __call__(self, children):
        if len(children) == 1:
            return children[0]
        else:
            return self.next_filter(children)

class TokenWrapper(TreeFilter):
    "Used for fixing the results of scanless parsing"

    def __init__(self, next_filter, token_name):
        super(TokenWrapper, self).__init__(next_filter)
        self.token_name = token_name

    @classmethod
    def create_if_required(cls, rule, **kwargs):
        if rule.options and rule.options.create_token:
            return Factory(cls, rule.options.create_token)

    def __call__(self, children):
        return self.next_filter( [Token(self.token_name, ''.join(children))] )

class ChildFilter(TreeFilter):
    """Filter and / or expand child items of a tree"""

    filtered_rules = None

    def __init__(self, node_builder, to_include):
        super(ChildFilter, self).__init__(node_builder)
        self.to_include = to_include

    @classmethod
    def create_if_required(cls, rule, rules = None, filtered_nonterms = None, filtered_terms = None, keep_all_tokens = False, **kwargs):
        ### If nonterm starting with _ -> expand
        def _should_expand(sym):
            return not is_terminal(sym) and sym.startswith('_')

        if rule.options:
            keep_all_tokens = keep_all_tokens or rule.options.keep_all_tokens

        ### Build a set of inclusions/expansions:
        to_include = [(i, _should_expand(sym)) for i, sym in enumerate(rule.expansion)
                if keep_all_tokens or sym not in filtered_nonterms | filtered_terms]

        if len(to_include) < len(rule.expansion) or any(to_expand for i, to_expand in to_include):
            return Factory(ChildFilter, to_include)

    def __call__(self, children):
        filtered = []
        for i, to_expand in self.to_include:
            if to_expand:
                filtered += children[i].children
            else:
                filtered.append(children[i])

        return self.next_filter(filtered)

class PropagatePositions(TreeFilter):
    def __init__(self, node_builder):
        self.node_builder = node_builder

    @classmethod
    def create_if_required(cls, rule, propagate_positions = False, **kwargs):
        if propagate_positions:
            return PropagatePositions

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

class Callback(object):
    pass

class ParseTreeBuilder(object):
    tree_filters = [
        NodeBuilder,
        CallUserTransformer,
        ExpandSingleChild,
        TokenWrapper,
        ChildFilter,
        PropagatePositions
    ]

    def __init__(self, rules, tree_class, propagate_positions=False, keep_all_tokens=False):
        self.tree_class = tree_class
        self.propagate_positions = propagate_positions
        self.keep_all_tokens = keep_all_tokens
        self.filtered_terms = set([sym for rule in rules for sym in rule.expansion if is_terminal(sym) and sym.startswith('_')])
        self.filtered_nonterms = set([rule.origin for rule in rules if rule.options and rule.options.filter_out])
        self.rules = rules
        self.user_aliases = {}

    def create_callback(self, transformer = None):
        callback = Callback()

        for rule in self.rules:
            ### Let each Filter decide if it needs to filter this rule.
            #   If it does, it will return a callable which will instantiate
            #   a filter instance.
            tree_filter_chain = filter(None, [
                    tree_filter.create_if_required(rule,
                        tree_class = self.tree_class,
                        propagate_positions = self.propagate_positions,
                        keep_all_tokens = self.keep_all_tokens,
                        rules = self.rules,
                        filtered_nonterms = self.filtered_nonterms,
                        filtered_terms = self.filtered_terms,
                        transformer = transformer
                    )
                    for tree_filter in ParseTreeBuilder.tree_filters
                ])

            ### Now ask each valid filter to instantiate itself, passing the 
            #   previous (next) filter to build the chain.
            next_filter = None
            for tree_filter in tree_filter_chain:
                next_filter = tree_filter(next_filter)

            self.user_aliases[rule] = rule.alias
            rule.alias = '_callback_%s_%s' % (rule.origin, '_'.join(rule.expansion))
            if hasattr(callback, rule.alias):
                raise GrammarError("Rule '%s' already exists" % (rule,))
            setattr(callback, rule.alias, next_filter)

        return callback

###}
