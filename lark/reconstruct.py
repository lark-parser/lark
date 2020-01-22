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

class Reconstructor:
    def __init__(self, parser, term_subs={}):
        # XXX TODO calling compile twice returns different results!
        assert parser.options.maybe_placeholders == False
        tokens, rules, _grammar_extra = parser.grammar.compile(parser.options.start)

        self.write_tokens = WriteTokensTransformer({t.name:t for t in tokens}, term_subs)
        self.rules = list(self._build_recons_rules(rules))
        self.rules.reverse()

        # Choose the best rule from each group of {rule => [rule.alias]}, since we only really need one derivation.
        self.rules = best_from_group(self.rules, lambda r: r, lambda r: -len(r.expansion))

        self.rules.sort(key=lambda r: len(r.expansion))
        callbacks = {rule: rule.alias for rule in self.rules}   # TODO pass callbacks through dict, instead of alias?
        self.parser = earley.Parser(ParserConf(self.rules, callbacks, parser.options.start),
                                    self._match, resolve_ambiguity=True)

    def _build_recons_rules(self, rules):
        expand1s = {r.origin for r in rules if r.options.expand1}

        aliases = defaultdict(list)
        for r in rules:
            if r.alias:
                aliases[r.origin].append( r.alias )

        rule_names = {r.origin for r in rules}
        nonterminals = {sym for sym in rule_names
                       if sym.name.startswith('_') or sym in expand1s or sym in aliases }

        for r in rules:
            recons_exp = [sym if sym in nonterminals else Terminal(sym.name)
                          for sym in r.expansion if not is_discarded_terminal(sym)]

            # Skip self-recursive constructs
            if recons_exp == [r.origin]:
                continue

            sym = NonTerminal(r.alias) if r.alias else r.origin

            yield Rule(sym, recons_exp, alias=MakeMatchTree(sym.name, r.expansion))

        for origin, rule_aliases in aliases.items():
            for alias in rule_aliases:
                yield Rule(origin, [Terminal(alias)], alias=MakeMatchTree(origin.name, [NonTerminal(alias)]))
            yield Rule(origin, [Terminal(origin.name)], alias=MakeMatchTree(origin.name, [origin]))

    def _match(self, term, token):
        if isinstance(token, Tree):
            return Terminal(token.data) == term
        elif isinstance(token, Token):
            return term == Terminal(token.type)
        assert False

    def _reconstruct(self, tree):
        # TODO: ambiguity?
        unreduced_tree = self.parser.parse(tree.children, tree.data)   # find a full derivation
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
