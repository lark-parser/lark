"""Grammar transformation classes for Lark.

Contains transformer and visitor classes used during grammar compilation:
PrepareLiterals, TerminalTreeToPattern, ApplyTemplates, EBNF_to_BNF,
PrepareAnonTerminals, SimplifyRule_Visitor, RuleTreeToText, ValidateSymbols,
PrepareGrammar, FindRuleSize, and helper functions.
"""

from collections import namedtuple
from copy import copy, deepcopy
from ast import literal_eval
from typing import List, Tuple, Union, Callable, Dict, Optional, Sequence, Generator

from .utils import classify_bool, is_id_continue, is_id_start, small_factors, OrderedSet, Serialize
from .lexer import Token, TerminalDef, PatternStr, PatternRE, Pattern
from .grammar import RuleOptions, Rule, Terminal, NonTerminal, Symbol, TOKEN_DEFAULT_PRIORITY
from .utils import classify, dedup_list
from .exceptions import GrammarError

from .tree import Tree, SlottedTree as ST
from .visitors import Transformer, Visitor, v_args, Transformer_InPlace, Transformer_NonRecursive
inline_args = v_args(inline=True)


_EMPTY = Symbol('__empty__')

_TERMINAL_NAMES = {
    '.' : 'DOT',
    ',' : 'COMMA',
    ':' : 'COLON',
    ';' : 'SEMICOLON',
    '+' : 'PLUS',
    '-' : 'MINUS',
    '*' : 'STAR',
    '/' : 'SLASH',
    '\\' : 'BACKSLASH',
    '|' : 'VBAR',
    '?' : 'QMARK',
    '!' : 'BANG',
    '@' : 'AT',
    '#' : 'HASH',
    '$' : 'DOLLAR',
    '%' : 'PERCENT',
    '^' : 'CIRCUMFLEX',
    '&' : 'AMPERSAND',
    '_' : 'UNDERSCORE',
    '<' : 'LESSTHAN',
    '>' : 'MORETHAN',
    '=' : 'EQUAL',
    '"' : 'DBLQUOTE',
    '\'' : 'QUOTE',
    '`' : 'BACKQUOTE',
    '~' : 'TILDE',
    '(' : 'LPAR',
    ')' : 'RPAR',
    '{' : 'LBRACE',
    '}' : 'RBRACE',
    '[' : 'LSQB',
    ']' : 'RSQB',
    '\n' : 'NEWLINE',
    '\r\n' : 'CRLF',
    '\t' : 'TAB',
    ' ' : 'SPACE',
}

# Value 5 keeps the number of states in the lalr parser somewhat minimal
# It isn't optimal, but close to it. See PR #949
SMALL_FACTOR_THRESHOLD = 5
# The Threshold whether repeat via ~ are split up into different rules
# 50 is chosen since it keeps the number of states low and therefore lalr analysis time low,
# while not being to overaggressive and unnecessarily creating rules that might create shift/reduce conflicts.
# (See PR #949)
REPEAT_BREAK_THRESHOLD = 50


class FindRuleSize(Transformer):
    def __init__(self, keep_all_tokens: bool):
        self.keep_all_tokens = keep_all_tokens

    def _will_not_get_removed(self, sym: Symbol) -> bool:
        if isinstance(sym, NonTerminal):
            return not sym.name.startswith('_')
        if isinstance(sym, Terminal):
            return self.keep_all_tokens or not sym.filter_out
        if sym is _EMPTY:
            return False
        assert False, sym

    def _args_as_int(self, args: List[Union[int, Symbol]]) -> Generator[int, None, None]:
        for a in args:
            if isinstance(a, int):
                yield a
            elif isinstance(a, Symbol):
                yield 1 if self._will_not_get_removed(a) else 0
            else:
                assert False

    def expansion(self, args) -> int:
        return sum(self._args_as_int(args))

    def expansions(self, args) -> int:
        return max(self._args_as_int(args))


@inline_args
class EBNF_to_BNF(Transformer_InPlace):
    def __init__(self):
        self.new_rules = []
        self.rules_cache = {}
        self.prefix = 'anon'
        self.i = 0
        self.rule_options = None

    def _name_rule(self, inner: str):
        new_name = '__%s_%s_%d' % (self.prefix, inner, self.i)
        self.i += 1
        return new_name

    def _add_rule(self, key, name, expansions):
        t = NonTerminal(name)
        self.new_rules.append((name, expansions, self.rule_options))
        self.rules_cache[key] = t
        return t

    def _add_recurse_rule(self, type_: str, expr: Tree):
        try:
            return self.rules_cache[expr]
        except KeyError:
            new_name = self._name_rule(type_)
            t = NonTerminal(new_name)
            tree = ST('expansions', [
                ST('expansion', [expr]),
                ST('expansion', [t, expr])
            ])
            return self._add_rule(expr, new_name, tree)

    def _add_repeat_rule(self, a, b, target, atom):
        """Generate a rule that repeats target ``a`` times, and repeats atom ``b`` times.

        When called recursively (into target), it repeats atom for x(n) times, where:
            x(0) = 1
            x(n) = a(n) * x(n-1) + b

        Example rule when a=3, b=4:

            new_rule: target target target atom atom atom atom

        """
        key = (a, b, target, atom)
        try:
            return self.rules_cache[key]
        except KeyError:
            new_name = self._name_rule('repeat_a%d_b%d' % (a, b))
            tree = ST('expansions', [ST('expansion', [target] * a + [atom] * b)])
            return self._add_rule(key, new_name, tree)

    def _add_repeat_opt_rule(self, a, b, target, target_opt, atom):
        """Creates a rule that matches atom 0 to (a*n+b)-1 times.

        When target matches n times atom, and target_opt 0 to n-1 times target_opt,

        First we generate target * i followed by target_opt, for i from 0 to a-1
        These match 0 to n*a - 1 times atom

        Then we generate target * a followed by atom * i, for i from 0 to b-1
        These match n*a to n*a + b-1 times atom

        The created rule will not have any shift/reduce conflicts so that it can be used with lalr

        Example rule when a=3, b=4:

            new_rule: target_opt
                    | target target_opt
                    | target target target_opt

                    | target target target
                    | target target target atom
                    | target target target atom atom
                    | target target target atom atom atom

        """
        key = (a, b, target, atom, "opt")
        try:
            return self.rules_cache[key]
        except KeyError:
            new_name = self._name_rule('repeat_a%d_b%d_opt' % (a, b))
            tree = ST('expansions', [
                ST('expansion', [target]*i + [target_opt]) for i in range(a)
            ] + [
                ST('expansion', [target]*a + [atom]*i) for i in range(b)
            ])
            return self._add_rule(key, new_name, tree)

    def _generate_repeats(self, rule: Tree, mn: int, mx: int):
        """Generates a rule tree that repeats ``rule`` exactly between ``mn`` to ``mx`` times.
        """
        # For a small number of repeats, we can take the naive approach
        if mx < REPEAT_BREAK_THRESHOLD:
            return ST('expansions', [ST('expansion', [rule] * n) for n in range(mn, mx + 1)])

        # For large repeat values, we break the repetition into sub-rules.
        # We treat ``rule~mn..mx`` as ``rule~mn rule~0..(diff=mx-mn)``.
        # We then use small_factors to split up mn and diff up into values [(a, b), ...]
        # This values are used with the help of _add_repeat_rule and _add_repeat_rule_opt
        # to generate a complete rule/expression that matches the corresponding number of repeats
        mn_target = rule
        for a, b in small_factors(mn, SMALL_FACTOR_THRESHOLD):
            mn_target = self._add_repeat_rule(a, b, mn_target, rule)
        if mx == mn:
            return mn_target

        diff = mx - mn + 1  # We add one because _add_repeat_opt_rule generates rules that match one less
        diff_factors = small_factors(diff, SMALL_FACTOR_THRESHOLD)
        diff_target = rule  # Match rule 1 times
        diff_opt_target = ST('expansion', [])  # match rule 0 times (e.g. up to 1 -1 times)
        for a, b in diff_factors[:-1]:
            diff_opt_target = self._add_repeat_opt_rule(a, b, diff_target, diff_opt_target, rule)
            diff_target = self._add_repeat_rule(a, b, diff_target, rule)

        a, b = diff_factors[-1]
        diff_opt_target = self._add_repeat_opt_rule(a, b, diff_target, diff_opt_target, rule)

        return ST('expansions', [ST('expansion', [mn_target] + [diff_opt_target])])

    def expr(self, rule: Tree, op: Token, *args):
        if op.value == '?':
            empty = ST('expansion', [])
            return ST('expansions', [rule, empty])
        elif op.value == '+':
            # a : b c+ d
            #   -->
            # a : b _c d
            # _c : _c c | c;
            return self._add_recurse_rule('plus', rule)
        elif op.value == '*':
            # a : b c* d
            #   -->
            # a : b _c? d
            # _c : _c c | c;
            new_name = self._add_recurse_rule('star', rule)
            return ST('expansions', [new_name, ST('expansion', [])])
        elif op.value == '~':
            if len(args) == 1:
                mn = mx = int(args[0])
            else:
                mn, mx = map(int, args)
                if mx < mn or mn < 0:
                    raise GrammarError("Bad Range for %s (%d..%d isn't allowed)" % (rule, mn, mx))

            return self._generate_repeats(rule, mn, mx)

        assert False, op

    def maybe(self, rule: Tree):
        keep_all_tokens = self.rule_options and self.rule_options.keep_all_tokens
        rule_size = FindRuleSize(keep_all_tokens).transform(rule)
        empty = ST('expansion', [_EMPTY] * rule_size)
        return ST('expansions', [rule, empty])


class SimplifyRule_Visitor(Visitor):

    @staticmethod
    def _flatten(tree: Tree):
        while tree.expand_kids_by_data(tree.data):
            pass

    def expansion(self, tree: Tree):
        # rules_list unpacking
        # a : b (c|d) e
        #  -->
        # a : b c e | b d e
        #
        # In AST terms:
        # expansion(b, expansions(c, d), e)
        #   -->
        # expansions( expansion(b, c, e), expansion(b, d, e) )

        self._flatten(tree)

        for i, child in enumerate(tree.children):
            if isinstance(child, Tree) and child.data == 'expansions':
                tree.data = 'expansions'
                tree.children = [self.visit(ST('expansion', [option if i == j else other
                                                             for j, other in enumerate(tree.children)]))
                                 for option in dedup_list(child.children)]
                self._flatten(tree)
                break

    def alias(self, tree):
        rule, alias_name = tree.children
        if rule.data == 'expansions':
            aliases = []
            for child in tree.children[0].children:
                aliases.append(ST('alias', [child, alias_name]))
            tree.data = 'expansions'
            tree.children = aliases

    def expansions(self, tree: Tree):
        self._flatten(tree)
        # Ensure all children are unique
        if len(set(tree.children)) != len(tree.children):
            tree.children = dedup_list(tree.children)   # dedup is expensive, so try to minimize its use


class RuleTreeToText(Transformer):
    def expansions(self, x):
        return x

    def expansion(self, symbols):
        return symbols, None

    def alias(self, x):
        (expansion, _alias), alias = x
        assert _alias is None, (alias, expansion, '-', _alias)  # Double alias not allowed
        return expansion, alias.name


class PrepareAnonTerminals(Transformer_InPlace):
    """Create a unique list of anonymous terminals. Attempt to give meaningful names to them when we add them"""

    def __init__(self, terminals):
        self.terminals = terminals
        self.term_set = {td.name for td in self.terminals}
        self.term_reverse = {td.pattern: td for td in terminals}
        self.i = 0
        self.rule_options = None

    @inline_args
    def pattern(self, p):
        value = p.value
        if p in self.term_reverse and p.flags != self.term_reverse[p].pattern.flags:
            raise GrammarError(u'Conflicting flags for the same terminal: %s' % p)

        term_name = None

        if isinstance(p, PatternStr):
            try:
                # If already defined, use the user-defined terminal name
                term_name = self.term_reverse[p].name
            except KeyError:
                # Try to assign an indicative anon-terminal name
                try:
                    term_name = _TERMINAL_NAMES[value]
                except KeyError:
                    if value and is_id_continue(value) and is_id_start(value[0]) and value.upper() not in self.term_set:
                        term_name = value.upper()

                if term_name in self.term_set:
                    term_name = None

        elif isinstance(p, PatternRE):
            if p in self.term_reverse:  # Kind of a weird placement.name
                term_name = self.term_reverse[p].name
        else:
            assert False, p

        if term_name is None:
            term_name = '__ANON_%d' % self.i
            self.i += 1

        if term_name not in self.term_set:
            assert p not in self.term_reverse
            self.term_set.add(term_name)
            termdef = TerminalDef(term_name, p)
            self.term_reverse[p] = termdef
            self.terminals.append(termdef)

        filter_out = False if self.rule_options and self.rule_options.keep_all_tokens else isinstance(p, PatternStr)

        return Terminal(term_name, filter_out=filter_out)


class _ReplaceSymbols(Transformer_InPlace):
    """Helper for ApplyTemplates"""

    def __init__(self):
        self.names = {}

    def value(self, c):
        if len(c) == 1 and isinstance(c[0], Symbol) and c[0].name in self.names:
            return self.names[c[0].name]
        return self.__default__('value', c, None)

    def template_usage(self, c):
        name = c[0].name
        if name in self.names:
            return self.__default__('template_usage', [self.names[name]] + c[1:], None)
        return self.__default__('template_usage', c, None)


class ApplyTemplates(Transformer_InPlace):
    """Apply the templates, creating new rules that represent the used templates"""

    def __init__(self, rule_defs):
        self.rule_defs = rule_defs
        self.replacer = _ReplaceSymbols()
        self.created_templates = set()

    def template_usage(self, c):
        name = c[0].name
        args = c[1:]
        result_name = "%s{%s}" % (name, ",".join(a.name for a in args))
        if result_name not in self.created_templates:
            self.created_templates.add(result_name)
            (_n, params, tree, options) ,= (t for t in self.rule_defs if t[0] == name)
            assert len(params) == len(args), args
            result_tree = deepcopy(tree)
            self.replacer.names = dict(zip(params, args))
            self.replacer.transform(result_tree)
            self.rule_defs.append((result_name, [], result_tree, deepcopy(options)))
        return NonTerminal(result_name)


def _rfind(s, choices):
    return max(s.rfind(c) for c in choices)


def eval_escaping(s):
    w = ''
    i = iter(s)
    for n in i:
        w += n
        if n == '\\':
            try:
                n2 = next(i)
            except StopIteration:
                raise GrammarError("Literal ended unexpectedly (bad escaping): `%r`" % s)
            if n2 == '\\':
                w += '\\\\'
            elif n2 not in 'Uuxnftr':
                w += '\\'
            w += n2
    w = w.replace('\\"', '"').replace("'", "\\'")

    to_eval = "u'''%s'''" % w
    try:
        s = literal_eval(to_eval)
    except SyntaxError as e:
        raise GrammarError(s, e)

    return s


def _literal_to_pattern(literal):
    assert isinstance(literal, Token)
    v = literal.value
    flag_start = _rfind(v, '/"')+1
    assert flag_start > 0
    flags = v[flag_start:]
    assert all(f in 'imslux' for f in flags), flags

    if literal.type == 'STRING' and '\n' in v:
        raise GrammarError('You cannot put newlines in string literals')

    if literal.type == 'REGEXP' and '\n' in v and 'x' not in flags:
        raise GrammarError('You can only use newlines in regular expressions '
                           'with the `x` (verbose) flag')

    v = v[:flag_start]
    assert v[0] == v[-1] and v[0] in '"/'
    x = v[1:-1]

    s = eval_escaping(x)

    if s == "":
        raise GrammarError("Empty terminals are not allowed (%s)" % literal)

    if literal.type == 'STRING':
        s = s.replace('\\\\', '\\')
        return PatternStr(s, flags, raw=literal.value)
    elif literal.type == 'REGEXP':
        return PatternRE(s, flags, raw=literal.value)
    else:
        assert False, 'Invariant failed: literal.type not in ["STRING", "REGEXP"]'


@inline_args
class PrepareLiterals(Transformer_InPlace):
    def literal(self, literal):
        return ST('pattern', [_literal_to_pattern(literal)])

    def range(self, start, end):
        assert start.type == end.type == 'STRING'
        start = start.value[1:-1]
        end = end.value[1:-1]
        assert len(eval_escaping(start)) == len(eval_escaping(end)) == 1
        regexp = '[%s-%s]' % (start, end)
        return ST('pattern', [PatternRE(regexp)])


def _make_joined_pattern(regexp, flags_set) -> PatternRE:
    return PatternRE(regexp, ())

class TerminalTreeToPattern(Transformer_NonRecursive):
    def pattern(self, ps):
        p ,= ps
        return p

    def expansion(self, items: List[Pattern]) -> Pattern:
        if not items:
            return PatternStr('')

        if len(items) == 1:
            return items[0]

        pattern = ''.join(i.to_regexp() for i in items)
        return _make_joined_pattern(pattern, {i.flags for i in items})

    def expansions(self, exps: List[Pattern]) -> Pattern:
        if len(exps) == 1:
            return exps[0]

        # Do a bit of sorting to make sure that the longest option is returned
        # (Python's re module otherwise prefers just 'l' when given (l|ll) and both could match)
        exps.sort(key=lambda x: (-x.max_width, -x.min_width, -len(x.value)))

        pattern = '(?:%s)' % ('|'.join(i.to_regexp() for i in exps))
        return _make_joined_pattern(pattern, {i.flags for i in exps})

    def expr(self, args) -> Pattern:
        inner: Pattern
        inner, op = args[:2]
        if op == '~':
            if len(args) == 3:
                op = "{%d}" % int(args[2])
            else:
                mn, mx = map(int, args[2:])
                if mx < mn:
                    raise GrammarError("Bad Range for %s (%d..%d isn't allowed)" % (inner, mn, mx))
                op = "{%d,%d}" % (mn, mx)
        else:
            assert len(args) == 2
        return PatternRE('(?:%s)%s' % (inner.to_regexp(), op), inner.flags)

    def maybe(self, expr):
        return self.expr(expr + ['?'])

    def alias(self, t):
        raise GrammarError("Aliasing not allowed in terminals (You used -> in the wrong place)")

    def value(self, v):
        return v[0]


class ValidateSymbols(Transformer_InPlace):
    def value(self, v):
        v ,= v
        assert isinstance(v, (Tree, Symbol))
        return v


def nr_deepcopy_tree(t):
    """Deepcopy tree `t` without recursion"""
    return Transformer_NonRecursive(False).transform(t)


@inline_args
class PrepareGrammar(Transformer_InPlace):
    def terminal(self, name):
        return Terminal(str(name), filter_out=name.startswith('_'))

    def nonterminal(self, name):
        return NonTerminal(name.value)


def _find_used_symbols(tree):
    assert tree.data == 'expansions'
    return {t.name for x in tree.find_data('expansion')
            for t in x.scan_values(lambda t: isinstance(t, Symbol))}
