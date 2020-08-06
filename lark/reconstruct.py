import unicodedata
from collections import defaultdict

from .tree import Tree
from .visitors import Transformer_InPlace
from .common import ParserConf
from .lexer import Token, PatternStr
from .parsers import earley
from .grammar import Rule, Terminal, NonTerminal



def is_discarded_terminal(t):
    return t.is_term and t.filter_out

def is_iter_empty(i):
    try:
        _ = next(i)
        return False
    except StopIteration:
        return True


class WriteTokensTransformer(Transformer_InPlace):
    "Inserts discarded tokens into their correct place, according to the rules of grammar"

    def __init__(self, tokens, term_subs):
        self.tokens = tokens
        self.term_subs = term_subs

    def __default__(self, data, children, meta):
        if not getattr(meta, 'match_tree', False):
            return Tree(data, children)

        iter_args = iter(children)
        to_write = []
        for sym in meta.orig_expansion:
            if is_discarded_terminal(sym):
                try:
                    v = self.term_subs[sym.name](sym)
                except KeyError:
                    t = self.tokens[sym.name]
                    if not isinstance(t.pattern, PatternStr):
                        raise NotImplementedError("Reconstructing regexps not supported yet: %s" % t)

                    v = t.pattern.value
                to_write.append(v)
            else:
                x = next(iter_args)
                if isinstance(x, list):
                    to_write += x
                else:
                    if isinstance(x, Token):
                        assert Terminal(x.type) == sym, x
                    else:
                        assert NonTerminal(x.data) == sym, (sym, x)
                    to_write.append(x)

        assert is_iter_empty(iter_args)
        return to_write


class MatchTree(Tree):
    pass

class MakeMatchTree:
    def __init__(self, name, expansion):
        self.name = name
        self.expansion = expansion

    def __call__(self, args):
        t = MatchTree(self.name, args)
        t.meta.match_tree = True
        t.meta.orig_expansion = self.expansion
        return t

def best_from_group(seq, group_key, cmp_key):
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


def make_recons_rule(origin, expansion, old_expansion):
    return Rule(origin, expansion, alias=MakeMatchTree(origin.name, old_expansion))

def make_recons_rule_to_term(origin, term):
    return make_recons_rule(origin, [Terminal(term.name)], [term])


class Reconstructor:
    """
    A Reconstructor that will, given a full parse Tree, generate source code.
    Pass `term_subs`, a dictionary of [Terminal name as str] to [output text as str]
    to say what discarded Terminals should be written as.
    """
    def __init__(self, parser, term_subs=None):
        # XXX TODO calling compile twice returns different results!
        assert parser.options.maybe_placeholders == False
        if term_subs is None:
            term_subs = {}
        tokens, rules, _grammar_extra = parser.grammar.compile(parser.options.start)

        self.write_tokens = WriteTokensTransformer({t.name:t for t in tokens}, term_subs)
        self.rules_for_root = defaultdict(list)

        self.rules = list(self._build_recons_rules(rules))
        self.rules.reverse()

        # Choose the best rule from each group of {rule => [rule.alias]}, since we only really need one derivation.
        self.rules = best_from_group(self.rules, lambda r: r, lambda r: -len(r.expansion))

        self.rules.sort(key=lambda r: len(r.expansion))
        self.parser = parser
        self._parser_cache = {}

    def _build_recons_rules(self, rules):
        expand1s = {r.origin for r in rules if r.options.expand1}

        aliases = defaultdict(list)
        for r in rules:
            if r.alias:
                aliases[r.origin].append( r.alias )

        rule_names = {r.origin for r in rules}
        nonterminals = {sym for sym in rule_names
                       if sym.name.startswith('_') or sym in expand1s or sym in aliases }

        seen = set()
        for r in rules:
            recons_exp = [sym if sym in nonterminals else Terminal(sym.name)
                          for sym in r.expansion if not is_discarded_terminal(sym)]

            # Skip self-recursive constructs
            if recons_exp == [r.origin] and r.alias is None:
                continue

            sym = NonTerminal(r.alias) if r.alias else r.origin
            rule = make_recons_rule(sym, recons_exp, r.expansion)

            if sym in expand1s and len(recons_exp) != 1:
                self.rules_for_root[sym.name].append(rule)

                if sym.name not in seen:
                    yield make_recons_rule_to_term(sym, sym)
                    seen.add(sym.name)
            else:
                if sym.name.startswith('_') or sym in expand1s:
                    yield rule
                else:
                    self.rules_for_root[sym.name].append(rule)

        for origin, rule_aliases in aliases.items():
            for alias in rule_aliases:
                yield make_recons_rule_to_term(origin, NonTerminal(alias))
            yield make_recons_rule_to_term(origin, origin)

    def _match(self, term, token):
        if isinstance(token, Tree):
            return Terminal(token.data) == term
        elif isinstance(token, Token):
            return term == Terminal(token.type)
        assert False

    def _reconstruct(self, tree):
        # TODO: ambiguity?
        try:
            parser = self._parser_cache[tree.data]
        except KeyError:
            rules = self.rules + best_from_group(
                self.rules_for_root[tree.data], lambda r: r, lambda r: -len(r.expansion)
            )

            rules.sort(key=lambda r: len(r.expansion))

            callbacks = {rule: rule.alias for rule in rules}  # TODO pass callbacks through dict, instead of alias?
            parser = earley.Parser(ParserConf(rules, callbacks, [tree.data]), self._match, resolve_ambiguity=True)
            self._parser_cache[tree.data] = parser

        unreduced_tree = parser.parse(tree.children, tree.data)   # find a full derivation
        assert unreduced_tree.data == tree.data
        res = self.write_tokens.transform(unreduced_tree)
        for item in res:
            if isinstance(item, Tree):
                for x in self._reconstruct(item):
                    yield x
            else:
                yield item

    def reconstruct(self, tree):
        x = self._reconstruct(tree)
        y = []
        prev_item = ''
        for item in x:
            if prev_item and item and prev_item[-1].isalnum() and item[0].isalnum():
                y.append(' ')
            y.append(item)
            prev_item = item
        return ''.join(y)
