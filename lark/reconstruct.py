from collections import defaultdict

from .tree import Tree
from .visitors import Transformer_InPlace
from .common import ParserConf, PatternStr
from .lexer import Token
# from .parsers import earley, resolve_ambig
from .grammar import Rule, Terminal, NonTerminal

from .parser_frontends import Earley, CYK, LALR_TraditionalLexer



def is_discarded_terminal(t):
    return t.is_term and t.filter_out

def is_iter_empty(i):
    try:
        _ = next(i)
        return False
    except StopIteration:
        return True

class WriteTokensTransformer(Transformer_InPlace):
    def __init__(self, tokens):
        self.tokens = tokens

    def __default__(self, data, children, meta):
        #  if not isinstance(t, MatchTree):
            #  return t
        if not getattr(meta, 'match_tree', False):
            return Tree(data, children)

        iter_args = iter(children)
        to_write = []
        for sym in meta.orig_expansion:
            if is_discarded_terminal(sym):
                t = self.tokens[sym.name]
                if isinstance(t.pattern, PatternStr):
                    value = t.pattern.value
                else:
                    assert t.name == '_NEWLINE'
                    value = '\n'
                to_write.append(value)
            else:
                x = next(iter_args)
                if isinstance(x, list):
                    to_write += x
                else:
                    if isinstance(x, Token):
                        assert x.type == sym.name, (x.type, sym, x)
                    else:
                        assert NonTerminal(x.data) == sym, (sym, x)
                    to_write.append(x.value)

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


def make_recons_rule(origin, expansion, old_expansion):
    return Rule(origin, expansion, MakeMatchTree(origin.name, old_expansion))

def make_recons_rule_to_term(origin, term):
    return make_recons_rule(origin, [Terminal(term.name)], [term])

class Reconstructor:
    def __init__(self, parser):
        # XXX TODO calling compile twice returns different results!
        tokens, rules, _grammar_extra = parser.grammar.compile()

        self.write_tokens = WriteTokensTransformer({t.name:t for t in tokens})
        self.rules_for_root = defaultdict(list)
        self.rules = list(self._build_recons_rules(rules))
        self._parser_cache = {}  # Cache for reconstructor parser trees


    def _build_recons_rules(self, rules):
        expand1s = {r.origin for r in rules if r.options and r.options.expand1}

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

    def match2(self, term, token):
        return term.name == token.type


    def _reconstruct(self, tree):
        try:
            parser = self._parser_cache[tree.data]
        except KeyError:
            rules = self.rules + self.rules_for_root[tree.data]
            # parser = earley.Parser(ParserConf(rules, None, tree.data), self.match2,
            #                    resolve_ambiguity=resolve_ambig.standard_resolve_ambig)
            parser = Earley(None, ParserConf(rules, None, tree.data))
            self._parser_cache[tree.data] = parser

        x = []
        for c in tree.children:
            if isinstance(c, Tree):
                x.append(Token(c.data, c))
            elif isinstance(c, Token):
                x.append(Token(c.type, c))
            else:
                assert False, c
        unreduced_tree = parser.parse(x)   # find a full derivation
        assert unreduced_tree.data == tree.data
        res = self.write_tokens.transform(unreduced_tree)
        for item in res:
            if isinstance(item, Tree):
                for x in self._reconstruct(item):
                    yield x
            else:
                yield item

    def reconstruct(self, tree):
        # TODO: ambiguity?
        return ''.join(self._reconstruct(tree))

