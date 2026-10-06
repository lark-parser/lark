"""Tree matcher based on Lark grammar"""

import re
from typing import List, Dict
from collections import defaultdict

from . import Tree, Token, Lark
from .common import ParserConf
from .exceptions import ConfigurationError
from .parsers import earley
from .grammar import Rule, Terminal, NonTerminal


def is_discarded_terminal(t):
    return t.is_term and t.filter_out


class _MakeTreeMatch:
    def __init__(self, name, expansion):
        self.name = name
        self.expansion = expansion

    def __call__(self, args):
        t = Tree(self.name, args)
        t.meta.match_tree = True
        t.meta.orig_expansion = self.expansion
        return t


def _best_from_group(seq, group_key, cmp_key):
    d = {}
    for item in seq:
        key = group_key(item)
        if key in d:
            v1 = cmp_key(item)
            v2 = cmp_key(d[key])
            if v2 > v1:
                d[key] = item
        else:
            d[key] = item
    return list(d.values())


def _best_rules_from_group(rules: List[Rule]) -> List[Rule]:
    rules = _best_from_group(rules, lambda r: r, lambda r: -len(r.expansion))
    rules.sort(key=lambda r: len(r.expansion))
    return rules


def _match(term, token):
    if isinstance(token, Tree):
        name, _args = parse_rulename(term.name)
        return token.data == name
    elif isinstance(token, Token):
        return term == Terminal(token.type)
    assert False, (term, token)


def make_recons_rule(origin, expansion, old_expansion):
    return Rule(origin, expansion, alias=_MakeTreeMatch(origin.name, old_expansion))


def make_recons_rule_to_term(origin, term):
    return make_recons_rule(origin, [Terminal(term.name)], [term])


def _expand1_rules(rules, hidden_rules):
    # Underscored rules are flattened before ExpandSingleChild is applied.
    # Find which of them can contribute zero or one children to the shaped tree.
    empty, single = set(), set()
    changed = True
    while changed:
        changed = False
        for origin, alternatives in hidden_rules.items():
            for rule in alternatives:
                expansion = rule.expansion
                if origin not in empty and all(sym in empty for sym in expansion):
                    empty.add(origin)
                    changed = True
                if origin not in single and any(
                    (sym not in hidden_rules or sym in single)
                    and all(other in empty for j, other in enumerate(expansion) if i != j)
                    for i, sym in enumerate(expansion)
                ):
                    single.add(origin)
                    changed = True

    # Specialize only the hidden rules reached by a single-child derivation.
    # Keep the original callbacks, so discarded tokens retain their positions.
    pending = []

    def restrict(expansion, size):
        for index in range(len(expansion)) if size else (None,):
            result = []
            for i, sym in enumerate(expansion):
                count = int(i == index)
                if sym in hidden_rules:
                    if sym not in (single if count else empty):
                        break
                    pending.append((sym, count))
                    result.append(NonTerminal('%s$%d' % (sym.name, count)))
                elif count:
                    result.append(sym)
                else:
                    break
            else:
                yield result

    for rule in rules:
        for expansion in restrict(rule.expansion, 1):
            yield Rule(rule.origin, expansion, alias=rule.alias)

    seen = set()
    while pending:
        sym, size = pending.pop()
        if (sym, size) in seen:
            continue
        seen.add((sym, size))
        origin = NonTerminal('%s$%d' % (sym.name, size))
        for rule in hidden_rules[sym]:
            for expansion in restrict(rule.expansion, size):
                yield Rule(origin, expansion, alias=rule.alias)


def parse_rulename(s):
    "Parse rule names that may contain a template syntax (like rule{a, b, ...})"
    name, args_str = re.match(r'(\w+)(?:{(.+)})?', s).groups()
    args = args_str and [a.strip() for a in args_str.split(',')]
    return name, args



class ChildrenLexer:
    def __init__(self, children):
        self.children = children

    def lex(self, parser_state):
        return self.children

class TreeMatcher:
    """Match the elements of a tree node, based on an ontology
    provided by a Lark grammar.

    Supports templates and inlined rules (`rule{a, b,..}` and `_rule`)

    Initialize with an instance of Lark.
    """
    rules_for_root: Dict[str, List[Rule]]
    rules: List[Rule]
    parser: Lark

    def __init__(self, parser: Lark):
        # XXX TODO calling compile twice returns different results!
        assert not parser.options.maybe_placeholders

        if parser.options.postlex and parser.options.postlex.always_accept:
            # If postlexer's always_accept is used, we need to recompile the grammar with empty terminals-to-keep
            if not hasattr(parser, 'grammar'):
                raise ConfigurationError('Source grammar not available from cached parser, use cache_grammar=True'
                                         if parser.options.cache else "Source grammar not available!")
            self.tokens, rules, _extra = parser.grammar.compile(parser.options.start, set())
        else:
            self.tokens = list(parser.terminals)
            rules = list(parser.rules)

        self.rules_for_root = defaultdict(list)

        self.rules = list(self._build_recons_rules(rules))
        self.rules.reverse()

        # Choose the best rule from each group of {rule => [rule.alias]}, since we only really need one derivation.
        self.rules = _best_rules_from_group(self.rules)

        self.parser = parser
        self._parser_cache: Dict[str, earley.Parser] = {}

    def _build_recons_rules(self, rules: List[Rule]):
        "Convert tree-parsing/construction rules to tree-matching rules"
        expand1s = {r.origin for r in rules if r.options.expand1}

        aliases = defaultdict(list)
        for r in rules:
            if r.alias:
                aliases[r.origin].append(r.alias)

        rule_names = {r.origin for r in rules}
        nonterminals = {sym for sym in rule_names
                        if sym.name.startswith('_') or sym in expand1s or sym in aliases}

        seen = set()
        expand1_rules = []
        hidden_rules = defaultdict(list)
        for r in rules:
            recons_exp = [sym if sym in nonterminals else Terminal(sym.name)
                          for sym in r.expansion if not is_discarded_terminal(sym)]

            # Skip self-recursive constructs
            if recons_exp == [r.origin] and r.alias is None:
                continue

            sym = NonTerminal(r.alias) if r.alias else r.origin
            rule = make_recons_rule(sym, recons_exp, r.expansion)

            if sym in expand1s:
                self.rules_for_root[sym.name].append(rule)
                expand1_rules.append(rule)

                if sym.name not in seen:
                    yield make_recons_rule_to_term(sym, sym)
                    seen.add(sym.name)
            else:
                if sym.name.startswith('_'):
                    hidden_rules[sym].append(rule)
                    yield rule
                else:
                    self.rules_for_root[sym.name].append(rule)

        yield from _expand1_rules(expand1_rules, hidden_rules)

        for origin, rule_aliases in aliases.items():
            for alias in rule_aliases:
                yield make_recons_rule_to_term(origin, NonTerminal(alias))
            yield make_recons_rule_to_term(origin, origin)

    def match_tree(self, tree: Tree, rulename: str) -> Tree:
        """Match the elements of `tree` to the symbols of rule `rulename`.

        Parameters:
            tree (Tree): the tree node to match
            rulename (str): The expected full rule name (including template args)

        Returns:
            Tree: an unreduced tree that matches `rulename`

        Raises:
            UnexpectedToken: If no match was found.

        Note:
            It's the callers' responsibility to match the tree recursively.
        """
        if rulename:
            # validate
            name, _args = parse_rulename(rulename)
            assert tree.data == name
        else:
            rulename = tree.data

        # TODO: ambiguity?
        try:
            parser = self._parser_cache[rulename]
        except KeyError:
            rules = _best_rules_from_group(self.rules + self.rules_for_root[rulename])

            # TODO pass callbacks through dict, instead of alias?
            callbacks = {rule: rule.alias for rule in rules}
            conf = ParserConf(rules, callbacks, [rulename]) # type: ignore[arg-type]
            parser = earley.Parser(self.parser.lexer_conf, conf, _match, resolve_ambiguity=True)
            self._parser_cache[rulename] = parser

        # find a full derivation
        unreduced_tree: Tree = parser.parse(ChildrenLexer(tree.children), rulename)
        assert unreduced_tree.data == rulename
        return unreduced_tree
