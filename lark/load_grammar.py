"""Parses and creates Grammar objects"""

import os.path
import sys
from copy import copy, deepcopy
from io import open
import pkgutil
from ast import literal_eval
from numbers import Integral

from .utils import bfs, Py36, logger, classify_bool, is_id_continue, is_id_start
from .lexer import Token, TerminalDef, PatternStr, PatternRE

from .parse_tree_builder import ParseTreeBuilder
from .parser_frontends import ParsingFrontend
from .common import LexerConf, ParserConf
from .grammar import RuleOptions, Rule, Terminal, NonTerminal, Symbol
from .utils import classify, suppress, dedup_list, Str
from .exceptions import GrammarError, UnexpectedCharacters, UnexpectedToken

from .tree import Tree, SlottedTree as ST
from .visitors import Transformer, Visitor, v_args, Transformer_InPlace, Transformer_NonRecursive
inline_args = v_args(inline=True)

__path__ = os.path.dirname(__file__)
IMPORT_PATHS = ['grammars']

EXT = '.lark'

_RE_FLAGS = 'imslux'

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

# Grammar Parser
TERMINALS = {
    '_LPAR': r'\(',
    '_RPAR': r'\)',
    '_LBRA': r'\[',
    '_RBRA': r'\]',
    '_LBRACE': r'\{',
    '_RBRACE': r'\}',
    'OP': '[+*]|[?](?![a-z])',
    '_COLON': ':',
    '_COMMA': ',',
    '_OR': r'\|',
    '_DOT': r'\.(?!\.)',
    '_DOTDOT': r'\.\.',
    'TILDE': '~',
    'RULE': '!?[_?]?[a-z][_a-z0-9]*',
    'TERMINAL': '_?[A-Z][_A-Z0-9]*',
    'STRING': r'"(\\"|\\\\|[^"\n])*?"i?',
    'REGEXP': r'/(?!/)(\\/|\\\\|[^/])*?/[%s]*' % _RE_FLAGS,
    '_NL': r'(\r?\n)+\s*',
    'WS': r'[ \t]+',
    'COMMENT': r'\s*//[^\n]*',
    '_TO': '->',
    '_IGNORE': r'%ignore',
    '_OVERRIDE': r'%override',
    '_DECLARE': r'%declare',
    '_EXTEND': r'%extend',
    '_IMPORT': r'%import',
    'NUMBER': r'[+-]?\d+',
}

RULES = {
    'start': ['_list'],
    '_list':  ['_item', '_list _item'],
    '_item':  ['rule', 'term', 'ignore', 'import', 'declare', 'override', 'extend', '_NL'],

    'rule': ['RULE template_params _COLON expansions _NL',
             'RULE template_params _DOT NUMBER _COLON expansions _NL'],
    'template_params': ['_LBRACE _template_params _RBRACE',
                        ''],
    '_template_params': ['RULE',
                         '_template_params _COMMA RULE'],
    'expansions': ['alias',
                   'expansions _OR alias',
                   'expansions _NL _OR alias'],

    '?alias':     ['expansion _TO RULE', 'expansion'],
    'expansion': ['_expansion'],

    '_expansion': ['', '_expansion expr'],

    '?expr': ['atom',
              'atom OP',
              'atom TILDE NUMBER',
              'atom TILDE NUMBER _DOTDOT NUMBER',
              ],

    '?atom': ['_LPAR expansions _RPAR',
              'maybe',
              'value'],

    'value': ['terminal',
              'nonterminal',
              'literal',
              'range',
              'template_usage'],

    'terminal': ['TERMINAL'],
    'nonterminal': ['RULE'],

    '?name': ['RULE', 'TERMINAL'],

    'maybe': ['_LBRA expansions _RBRA'],
    'range': ['STRING _DOTDOT STRING'],

    'template_usage': ['RULE _LBRACE _template_args _RBRACE'],
    '_template_args': ['value',
                       '_template_args _COMMA value'],

    'term': ['TERMINAL _COLON expansions _NL',
             'TERMINAL _DOT NUMBER _COLON expansions _NL'],
    'override': ['_OVERRIDE rule',
                 '_OVERRIDE term'],
    'extend': ['_EXTEND rule',
               '_EXTEND term'],
    'ignore': ['_IGNORE expansions _NL'],
    'declare': ['_DECLARE _declare_args _NL'],
    'import': ['_IMPORT _import_path _NL',
               '_IMPORT _import_path _LPAR name_list _RPAR _NL',
               '_IMPORT _import_path _TO name _NL'],

    '_import_path': ['import_lib', 'import_rel'],
    'import_lib': ['_import_args'],
    'import_rel': ['_DOT _import_args'],
    '_import_args': ['name', '_import_args _DOT name'],

    'name_list': ['_name_list'],
    '_name_list': ['name', '_name_list _COMMA name'],

    '_declare_args': ['name', '_declare_args name'],
    'literal': ['REGEXP', 'STRING'],
}


@inline_args
class EBNF_to_BNF(Transformer_InPlace):
    def __init__(self):
        self.new_rules = []
        self.rules_by_expr = {}
        self.prefix = 'anon'
        self.i = 0
        self.rule_options = None

    def _add_recurse_rule(self, type_, expr):
        if expr in self.rules_by_expr:
            return self.rules_by_expr[expr]

        new_name = '__%s_%s_%d' % (self.prefix, type_, self.i)
        self.i += 1
        t = NonTerminal(new_name)
        tree = ST('expansions', [ST('expansion', [expr]), ST('expansion', [t, expr])])
        self.new_rules.append((new_name, tree, self.rule_options))
        self.rules_by_expr[expr] = t
        return t

    def expr(self, rule, op, *args):
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
            return ST('expansions', [ST('expansion', [rule] * n) for n in range(mn, mx+1)])
        assert False, op

    def maybe(self, rule):
        keep_all_tokens = self.rule_options and self.rule_options.keep_all_tokens

        def will_not_get_removed(sym):
            if isinstance(sym, NonTerminal):
                return not sym.name.startswith('_')
            if isinstance(sym, Terminal):
                return keep_all_tokens or not sym.filter_out
            assert False

        if any(rule.scan_values(will_not_get_removed)):
            empty = _EMPTY
        else:
            empty = ST('expansion', [])

        return ST('expansions', [rule, empty])


class SimplifyRule_Visitor(Visitor):

    @staticmethod
    def _flatten(tree):
        while True:
            to_expand = [i for i, child in enumerate(tree.children)
                         if isinstance(child, Tree) and child.data == tree.data]
            if not to_expand:
                break
            tree.expand_kids_by_index(*to_expand)

    def expansion(self, tree):
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

    def expansions(self, tree):
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
        return expansion, alias.value


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
                    if is_id_continue(value) and is_id_start(value[0]) and value.upper() not in self.term_set:
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
        if len(c) == 1 and isinstance(c[0], Token) and c[0].value in self.names:
            return self.names[c[0].value]
        return self.__default__('value', c, None)

    def template_usage(self, c):
        if c[0] in self.names:
            return self.__default__('template_usage', [self.names[c[0]].name] + c[1:], None)
        return self.__default__('template_usage', c, None)


class ApplyTemplates(Transformer_InPlace):
    """Apply the templates, creating new rules that represent the used templates"""

    def __init__(self, rule_defs):
        self.rule_defs = rule_defs
        self.replacer = _ReplaceSymbols()
        self.created_templates = set()

    def template_usage(self, c):
        name = c[0]
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
            elif n2 not in 'uxnftr':
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
    v = literal.value
    flag_start = _rfind(v, '/"')+1
    assert flag_start > 0
    flags = v[flag_start:]
    assert all(f in _RE_FLAGS for f in flags), flags

    if literal.type == 'STRING' and '\n' in v:
        raise GrammarError('You cannot put newlines in string literals')

    if literal.type == 'REGEXP' and '\n' in v and 'x' not in flags:
        raise GrammarError('You can only use newlines in regular expressions '
                           'with the `x` (verbose) flag')

    v = v[:flag_start]
    assert v[0] == v[-1] and v[0] in '"/'
    x = v[1:-1]

    s = eval_escaping(x)

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


def _make_joined_pattern(regexp, flags_set):
    # In Python 3.6, a new syntax for flags was introduced, that allows us to restrict the scope
    # of flags to a specific regexp group. We are already using it in `lexer.Pattern._get_flags`
    # However, for prior Python versions, we still need to use global flags, so we have to make sure
    # that there are no flag collisions when we merge several terminals.
    flags = ()
    if not Py36:
        if len(flags_set) > 1:
            raise GrammarError("Lark doesn't support joining terminals with conflicting flags in python <3.6!")
        elif len(flags_set) == 1:
            flags ,= flags_set

    return PatternRE(regexp, flags)


class TerminalTreeToPattern(Transformer):
    def pattern(self, ps):
        p ,= ps
        return p

    def expansion(self, items):
        assert items
        if len(items) == 1:
            return items[0]

        pattern = ''.join(i.to_regexp() for i in items)
        return _make_joined_pattern(pattern, {i.flags for i in items})

    def expansions(self, exps):
        if len(exps) == 1:
            return exps[0]

        pattern = '(?:%s)' % ('|'.join(i.to_regexp() for i in exps))
        return _make_joined_pattern(pattern, {i.flags for i in exps})

    def expr(self, args):
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


class PrepareSymbols(Transformer_InPlace):
    def value(self, v):
        v ,= v
        if isinstance(v, Tree):
            return v
        elif v.type == 'RULE':
            return NonTerminal(Str(v.value))
        elif v.type == 'TERMINAL':
            return Terminal(Str(v.value), filter_out=v.startswith('_'))
        assert False


def nr_deepcopy_tree(t):
    """Deepcopy tree `t` without recursion"""
    return Transformer_NonRecursive(False).transform(t)


class Grammar:
    def __init__(self, rule_defs, term_defs, ignore):
        self.term_defs = term_defs
        self.rule_defs = rule_defs
        self.ignore = ignore

    def compile(self, start, terminals_to_keep):
        # We change the trees in-place (to support huge grammars)
        # So deepcopy allows calling compile more than once.
        term_defs = deepcopy(list(self.term_defs))
        rule_defs = [(n,p,nr_deepcopy_tree(t),o) for n,p,t,o in self.rule_defs]

        # ===================
        #  Compile Terminals
        # ===================

        # Convert terminal-trees to strings/regexps

        for name, (term_tree, priority) in term_defs:
            if term_tree is None:  # Terminal added through %declare
                continue
            expansions = list(term_tree.find_data('expansion'))
            if len(expansions) == 1 and not expansions[0].children:
                raise GrammarError("Terminals cannot be empty (%s)" % name)

        transformer = PrepareLiterals() * TerminalTreeToPattern()
        terminals = [TerminalDef(name, transformer.transform(term_tree), priority)
                     for name, (term_tree, priority) in term_defs if term_tree]

        # =================
        #  Compile Rules
        # =================

        # 1. Pre-process terminals
        anon_tokens_transf = PrepareAnonTerminals(terminals)
        transformer = PrepareLiterals() * PrepareSymbols() * anon_tokens_transf  # Adds to terminals

        # 2. Inline Templates

        transformer *= ApplyTemplates(rule_defs)

        # 3. Convert EBNF to BNF (and apply step 1 & 2)
        ebnf_to_bnf = EBNF_to_BNF()
        rules = []
        i = 0
        while i < len(rule_defs):  # We have to do it like this because rule_defs might grow due to templates
            name, params, rule_tree, options = rule_defs[i]
            i += 1
            if len(params) != 0:  # Dont transform templates
                continue
            rule_options = RuleOptions(keep_all_tokens=True) if options and options.keep_all_tokens else None
            ebnf_to_bnf.rule_options = rule_options
            ebnf_to_bnf.prefix = name
            anon_tokens_transf.rule_options = rule_options
            tree = transformer.transform(rule_tree)
            res = ebnf_to_bnf.transform(tree)
            rules.append((name, res, options))
        rules += ebnf_to_bnf.new_rules

        assert len(rules) == len({name for name, _t, _o in rules}), "Whoops, name collision"

        # 4. Compile tree to Rule objects
        rule_tree_to_text = RuleTreeToText()

        simplify_rule = SimplifyRule_Visitor()
        compiled_rules = []
        for rule_content in rules:
            name, tree, options = rule_content
            simplify_rule.visit(tree)
            expansions = rule_tree_to_text.transform(tree)

            for i, (expansion, alias) in enumerate(expansions):
                if alias and name.startswith('_'):
                    raise GrammarError("Rule %s is marked for expansion (it starts with an underscore) and isn't allowed to have aliases (alias=%s)"% (name, alias))

                empty_indices = [x==_EMPTY for x in expansion]
                if any(empty_indices):
                    exp_options = copy(options) or RuleOptions()
                    exp_options.empty_indices = empty_indices
                    expansion = [x for x in expansion if x!=_EMPTY]
                else:
                    exp_options = options

                assert all(isinstance(x, Symbol) for x in expansion), expansion
                rule = Rule(NonTerminal(name), expansion, i, alias, exp_options)
                compiled_rules.append(rule)

        # Remove duplicates of empty rules, throw error for non-empty duplicates
        if len(set(compiled_rules)) != len(compiled_rules):
            duplicates = classify(compiled_rules, lambda x: x)
            for dups in duplicates.values():
                if len(dups) > 1:
                    if dups[0].expansion:
                        raise GrammarError("Rules defined twice: %s\n\n(Might happen due to colliding expansion of optionals: [] or ?)"
                                           % ''.join('\n  * %s' % i for i in dups))

                    # Empty rule; assert all other attributes are equal
                    assert len({(r.alias, r.order, r.options) for r in dups}) == len(dups)

            # Remove duplicates
            compiled_rules = list(set(compiled_rules))

        # Filter out unused rules
        while True:
            c = len(compiled_rules)
            used_rules = {s for r in compiled_rules
                            for s in r.expansion
                            if isinstance(s, NonTerminal)
                            and s != r.origin}
            used_rules |= {NonTerminal(s) for s in start}
            compiled_rules, unused = classify_bool(compiled_rules, lambda r: r.origin in used_rules)
            for r in unused:
                logger.debug("Unused rule: %s", r)
            if len(compiled_rules) == c:
                break

        # Filter out unused terminals
        used_terms = {t.name for r in compiled_rules
                             for t in r.expansion
                             if isinstance(t, Terminal)}
        terminals, unused = classify_bool(terminals, lambda t: t.name in used_terms or t.name in self.ignore or t.name in terminals_to_keep)
        if unused:
            logger.debug("Unused terminals: %s", [t.name for t in unused])

        return terminals, compiled_rules, self.ignore


class PackageResource(object):
    """
    Represents a path inside a Package. Used by `FromPackageLoader`
    """
    def __init__(self, pkg_name, path):
        self.pkg_name = pkg_name
        self.path = path

    def __str__(self):
        return "<%s: %s>" % (self.pkg_name, self.path)

    def __repr__(self):
        return "%s(%r, %r)" % (type(self).__name__, self.pkg_name, self.path)


class FromPackageLoader(object):
    """
    Provides a simple way of creating custom import loaders that load from packages via ``pkgutil.get_data`` instead of using `open`.
    This allows them to be compatible even from within zip files.

    Relative imports are handled, so you can just freely use them.

    pkg_name: The name of the package. You can probably provide `__name__` most of the time
    search_paths: All the path that will be search on absolute imports.
    """
    def __init__(self, pkg_name, search_paths=("", )):
        self.pkg_name = pkg_name
        self.search_paths = search_paths

    def __repr__(self):
        return "%s(%r, %r)" % (type(self).__name__, self.pkg_name, self.search_paths)

    def __call__(self, base_path, grammar_path):
        if base_path is None:
            to_try = self.search_paths
        else:
            # Check whether or not the importing grammar was loaded by this module.
            if not isinstance(base_path, PackageResource) or base_path.pkg_name != self.pkg_name:
                # Technically false, but FileNotFound doesn't exist in python2.7, and this message should never reach the end user anyway
                raise IOError()
            to_try = [base_path.path]
        for path in to_try:
            full_path = os.path.join(path, grammar_path)
            try:
                text = pkgutil.get_data(self.pkg_name, full_path)
            except IOError:
                continue
            else:
                return PackageResource(self.pkg_name, full_path), text.decode()
        raise IOError()


stdlib_loader = FromPackageLoader('lark', IMPORT_PATHS)



def resolve_term_references(term_dict):
    # TODO Solve with transitive closure (maybe)

    while True:
        changed = False
        for name, token_tree in term_dict.items():
            if token_tree is None:  # Terminal added through %declare
                continue
            for exp in token_tree.find_data('value'):
                item ,= exp.children
                if isinstance(item, Token):
                    if item.type == 'RULE':
                        raise GrammarError("Rules aren't allowed inside terminals (%s in %s)" % (item, name))
                    if item.type == 'TERMINAL':
                        term_value = term_dict[item]
                        assert term_value is not None
                        exp.children[0] = term_value
                        changed = True
        if not changed:
            break

    for name, term in term_dict.items():
        if term:    # Not just declared
            for child in term.children:
                ids = [id(x) for x in child.iter_subtrees()]
                if id(term) in ids:
                    raise GrammarError("Recursion in terminal '%s' (recursion is only allowed in rules, not terminals)" % name)


def options_from_rule(name, params, *x):
    if len(x) > 1:
        priority, expansions = x
        priority = int(priority)
    else:
        expansions ,= x
        priority = None
    params = [t.value for t in params.children] if params is not None else []  # For the grammar parser

    keep_all_tokens = name.startswith('!')
    name = name.lstrip('!')
    expand1 = name.startswith('?')
    name = name.lstrip('?')

    return name, params, expansions, RuleOptions(keep_all_tokens, expand1, priority=priority,
                                                 template_source=(name if params else None))


def symbols_from_strcase(expansion):
    return [Terminal(x, filter_out=x.startswith('_')) if x.isupper() else NonTerminal(x) for x in expansion]


@inline_args
class PrepareGrammar(Transformer_InPlace):
    def terminal(self, name):
        return name

    def nonterminal(self, name):
        return name


def _find_used_symbols(tree):
    assert tree.data == 'expansions'
    return {t for x in tree.find_data('expansion')
              for t in x.scan_values(lambda t: t.type in ('RULE', 'TERMINAL'))}


def _get_parser():
    try:
        return _get_parser.cache
    except AttributeError:
        terminals = [TerminalDef(name, PatternRE(value)) for name, value in TERMINALS.items()]

        rules = [options_from_rule(name, None, x) for name, x in RULES.items()]
        rules = [Rule(NonTerminal(r), symbols_from_strcase(x.split()), i, None, o)
                 for r, _p, xs, o in rules for i, x in enumerate(xs)]
        callback = ParseTreeBuilder(rules, ST).create_callback()
        import re
        lexer_conf = LexerConf(terminals, re, ['WS', 'COMMENT'])
        parser_conf = ParserConf(rules, callback, ['start'])
        lexer_conf.lexer_type = 'standard'
        parser_conf.parser_type = 'lalr'
        _get_parser.cache = ParsingFrontend(lexer_conf, parser_conf, {})
        return _get_parser.cache

GRAMMAR_ERRORS = [
        ('Incorrect type of value', ['a: 1\n']),
        ('Unclosed parenthesis', ['a: (\n']),
        ('Unmatched closing parenthesis', ['a: )\n', 'a: [)\n', 'a: (]\n']),
        ('Expecting rule or terminal definition (missing colon)', ['a\n', 'A\n', 'a->\n', 'A->\n', 'a A\n']),
        ('Illegal name for rules or terminals', ['Aa:\n']),
        ('Alias expects lowercase name', ['a: -> "a"\n']),
        ('Unexpected colon', ['a::\n', 'a: b:\n', 'a: B:\n', 'a: "a":\n']),
        ('Misplaced operator', ['a: b??', 'a: b(?)', 'a:+\n', 'a:?\n', 'a:*\n', 'a:|*\n']),
        ('Expecting option ("|") or a new rule or terminal definition', ['a:a\n()\n']),
        ('Terminal names cannot contain dots', ['A.B\n']),
        ('Expecting rule or terminal definition', ['"a"\n']),
        ('%import expects a name', ['%import "a"\n']),
        ('%ignore expects a value', ['%ignore %import\n']),
    ]

def _translate_parser_exception(parse, e):
        error = e.match_examples(parse, GRAMMAR_ERRORS, use_accepts=True)
        if error:
            return error
        elif 'STRING' in e.expected:
            return "Expecting a value"

def _parse_grammar(text, name, start='start'):
    try:
        tree = _get_parser().parse(text + '\n', start)
    except UnexpectedCharacters as e:
        context = e.get_context(text)
        raise GrammarError("Unexpected input at line %d column %d in %s: \n\n%s" %
                           (e.line, e.column, name, context))
    except UnexpectedToken as e:
        context = e.get_context(text)
        error = _translate_parser_exception(_get_parser().parse, e)
        if error:
            raise GrammarError("%s, at line %s column %s\n\n%s" % (error, e.line, e.column, context))
        raise

    return PrepareGrammar().transform(tree)


def _get_mangle(prefix, aliases, base_mangle=None):
    def mangle(s):
        if s in aliases:
            s = aliases[s]
        else:
            if s[0] == '_':
                s = '_%s__%s' % (prefix, s[1:])
            else:
                s = '%s__%s' % (prefix, s)
        if base_mangle is not None:
            s = base_mangle(s)
        return s
    return mangle

def _mangle_exp(exp, mangle):
    if mangle is None:
        return exp
    exp = deepcopy(exp) # TODO: is this needed
    for t in exp.iter_subtrees():
        for i, c in enumerate(t.children):
            if isinstance(c, Token) and c.type in ('RULE', 'TERMINAL'):
                t.children[i] = Token(c.type, mangle(c.value))
    return exp



class GrammarBuilder:
    def __init__(self, global_keep_all_tokens=False, import_paths=None):
        self.global_keep_all_tokens = global_keep_all_tokens
        self.import_paths = import_paths or []

        self._definitions = {}
        self._ignore_names = []

    def _is_term(self, name):
        # Imported terminals are of the form `Path__to__Grammar__file__TERMINAL_NAME`
        # Only the last part is the actual name, and the rest might contain mixed case
        return name.rpartition('__')[-1].isupper()

    def _grammar_error(self, msg, *names):
        args = {}
        for i, name in enumerate(names, start=1):
            postfix = '' if i == 1 else str(i)
            args['name' + postfix] = name
            args['type' + postfix] = lowercase_type = ("rule", "terminal")[self._is_term(name)]
            args['Type' + postfix] = lowercase_type.title()
        raise GrammarError(msg.format(**args))

    def _check_options(self, name, options):
        if self._is_term(name):
            if options is None:
                options = 1
            # if we don't use Integral here, we run into python2.7/python3 problems with long vs int
            elif not isinstance(options, Integral):
                raise GrammarError("Terminal require a single int as 'options' (e.g. priority), got %s" % (type(options),))
        else:
            if options is None:
                options = RuleOptions()
            elif not isinstance(options, RuleOptions):
                raise GrammarError("Rules require a RuleOptions instance as 'options'")
            if self.global_keep_all_tokens:
                options.keep_all_tokens = True
        return options


    def _define(self, name, exp, params=(), options=None, override=False):
        if name in self._definitions:
            if not override:
                self._grammar_error("{Type} '{name}' defined more than once", name)
        elif override:
            self._grammar_error("Cannot override a nonexisting {type} {name}", name)

        if name.startswith('__'):
            self._grammar_error('Names starting with double-underscore are reserved (Error at {name})', name)

        self._definitions[name] = (params, exp, self._check_options(name, options))

    def _extend(self, name, exp, params=(), options=None):
        if name not in self._definitions:
            self._grammar_error("Can't extend {type} {name} as it wasn't defined before", name)
        if tuple(params) != tuple(self._definitions[name][0]):
            self._grammar_error("Cannot extend {type} with different parameters: {name}", name)
        # TODO: think about what to do with 'options'
        base = self._definitions[name][1]

        while len(base.children) == 2:
            assert isinstance(base.children[0], Tree) and base.children[0].data == 'expansions', base
            base = base.children[0]
        base.children.insert(0, exp)

    def _ignore(self, exp_or_name):
        if isinstance(exp_or_name, str):
            self._ignore_names.append(exp_or_name)
        else:
            assert isinstance(exp_or_name, Tree)
            t = exp_or_name
            if t.data == 'expansions' and len(t.children) == 1:
                t2 ,= t.children
                if t2.data=='expansion' and len(t2.children) == 1:
                    item ,= t2.children
                    if item.data == 'value':
                        item ,= item.children
                        if isinstance(item, Token) and item.type == 'TERMINAL':
                            self._ignore_names.append(item.value)
                            return

            name = '__IGNORE_%d'% len(self._ignore_names)
            self._ignore_names.append(name)
            self._definitions[name] = ((), t, 1)

    def _declare(self, *names):
        for name in names:
            self._define(name, None)

    def _unpack_import(self, stmt, grammar_name):
        if len(stmt.children) > 1:
            path_node, arg1 = stmt.children
        else:
            path_node, = stmt.children
            arg1 = None

        if isinstance(arg1, Tree):  # Multi import
            dotted_path = tuple(path_node.children)
            names = arg1.children
            aliases = dict(zip(names, names))  # Can't have aliased multi import, so all aliases will be the same as names
        else:  # Single import
            dotted_path = tuple(path_node.children[:-1])
            if not dotted_path:
                name ,= path_node.children
                raise GrammarError("Nothing was imported from grammar `%s`" % name)
            name = path_node.children[-1]  # Get name from dotted path
            aliases = {name.value: (arg1 or name).value}  # Aliases if exist

        if path_node.data == 'import_lib':  # Import from library
            base_path = None
        else:  # Relative import
            if grammar_name == '<string>':  # Import relative to script file path if grammar is coded in script
                try:
                    base_file = os.path.abspath(sys.modules['__main__'].__file__)
                except AttributeError:
                    base_file = None
            else:
                base_file = grammar_name  # Import relative to grammar file path if external grammar file
            if base_file:
                if isinstance(base_file, PackageResource):
                    base_path = PackageResource(base_file.pkg_name, os.path.split(base_file.path)[0])
                else:
                    base_path = os.path.split(base_file)[0]
            else:
                base_path = os.path.abspath(os.path.curdir)

        return dotted_path, base_path, aliases

    def _unpack_definition(self, tree, mangle):
        if tree.data == 'rule':
            name, params, exp, opts = options_from_rule(*tree.children)
        else:
            name = tree.children[0].value
            params = ()     # TODO terminal templates
            opts = int(tree.children[1]) if len(tree.children) == 3 else 1 # priority
            exp = tree.children[-1]

        if mangle is not None:
            params = tuple(mangle(p) for p in params)
            name = mangle(name)

        exp = _mangle_exp(exp, mangle)
        return name, exp, params, opts


    def load_grammar(self, grammar_text, grammar_name="<?>", mangle=None):
        tree = _parse_grammar(grammar_text, grammar_name)

        imports = {}
        for stmt in tree.children:
            if stmt.data == 'import':
                dotted_path, base_path, aliases = self._unpack_import(stmt, grammar_name)
                try:
                    import_base_path, import_aliases = imports[dotted_path]
                    assert base_path == import_base_path, 'Inconsistent base_path for %s.' % '.'.join(dotted_path)
                    import_aliases.update(aliases)
                except KeyError:
                    imports[dotted_path] = base_path, aliases

        for dotted_path, (base_path, aliases) in imports.items():
            self.do_import(dotted_path, base_path, aliases, mangle)

        for stmt in tree.children:
            if stmt.data in ('term', 'rule'):
                self._define(*self._unpack_definition(stmt, mangle))
            elif stmt.data == 'override':
                r ,= stmt.children
                self._define(*self._unpack_definition(r, mangle), override=True)
            elif stmt.data == 'extend':
                r ,= stmt.children
                self._extend(*self._unpack_definition(r, mangle))
            elif stmt.data == 'ignore':
                # if mangle is not None, we shouldn't apply ignore, since we aren't in a toplevel grammar
                if mangle is None:
                    self._ignore(*stmt.children)
            elif stmt.data == 'declare':
                names = [t.value for t in stmt.children]
                if mangle is None:
                    self._declare(*names)
                else:
                    self._declare(*map(mangle, names))
            elif stmt.data == 'import':
                pass
            else:
                assert False, stmt


        term_defs = { name: exp
            for name, (_params, exp, _options) in self._definitions.items()
            if self._is_term(name)
        }
        resolve_term_references(term_defs)


    def _remove_unused(self, used):
        def rule_dependencies(symbol):
            if self._is_term(symbol):
                return []
            try:
                params, tree,_ = self._definitions[symbol]
            except KeyError:
                return []
            return _find_used_symbols(tree) - set(params)

        _used = set(bfs(used, rule_dependencies))
        self._definitions = {k: v for k, v in self._definitions.items() if k in _used}


    def do_import(self, dotted_path, base_path, aliases, base_mangle=None):
        assert dotted_path
        mangle = _get_mangle('__'.join(dotted_path), aliases, base_mangle)
        grammar_path = os.path.join(*dotted_path) + EXT
        to_try = self.import_paths + ([base_path] if base_path is not None else []) + [stdlib_loader]
        for source in to_try:
            try:
                if callable(source):
                    joined_path, text = source(base_path, grammar_path)
                else:
                    joined_path = os.path.join(source, grammar_path)
                    with open(joined_path, encoding='utf8') as f:
                        text = f.read()
            except IOError:
                continue
            else:
                gb = GrammarBuilder(self.global_keep_all_tokens, self.import_paths)
                gb.load_grammar(text, joined_path, mangle)
                gb._remove_unused(map(mangle, aliases))
                for name in gb._definitions:
                    if name in self._definitions:
                        raise GrammarError("Cannot import '%s' from '%s': Symbol already defined." % (name, grammar_path))

                self._definitions.update(**gb._definitions)
                break
        else:
            # Search failed. Make Python throw a nice error.
            open(grammar_path, encoding='utf8')
            assert False, "Couldn't import grammar %s, but a corresponding file was found at a place where lark doesn't search for it" % (dotted_path,)


    def validate(self):
        for name, (params, exp, _options) in self._definitions.items():
            for i, p in enumerate(params):
                if p in self._definitions:
                    raise GrammarError("Template Parameter conflicts with rule %s (in template %s)" % (p, name))
                if p in params[:i]:
                    raise GrammarError("Duplicate Template Parameter %s (in template %s)" % (p, name))

            if exp is None: # Remaining checks don't apply to abstract rules/terminals
                continue

            for temp in exp.find_data('template_usage'):
                sym = temp.children[0]
                args = temp.children[1:]
                if sym not in params:
                    if sym not in self._definitions:
                        self._grammar_error("Template '%s' used but not defined (in {type} {name})" % sym, name)
                    if len(args) != len(self._definitions[sym][0]):
                        expected, actual = len(self._definitions[sym][0]), len(args)
                        self._grammar_error("Wrong number of template arguments used for {name} "
                                            "(expected %s, got %s) (in {type2} {name2})" % (expected, actual), sym, name)

            for sym in _find_used_symbols(exp):
                if sym not in self._definitions and sym not in params:
                    self._grammar_error("{Type} '{name}' used but not defined (in {type2} {name2})", sym, name)

        if not set(self._definitions).issuperset(self._ignore_names):
            raise GrammarError("Terminals %s were marked to ignore but were not defined!" % (set(self._ignore_names) - set(self._definitions)))

    def build(self):
        self.validate()
        rule_defs = []
        term_defs = []
        for name, (params, exp, options) in self._definitions.items():
            if self._is_term(name):
                assert len(params) == 0
                term_defs.append((name, (exp, options)))
            else:
                rule_defs.append((name, params, exp, options))
        # resolve_term_references(term_defs)
        return Grammar(rule_defs, term_defs, self._ignore_names)

def load_grammar(grammar, source, import_paths, global_keep_all_tokens):
    builder = GrammarBuilder(global_keep_all_tokens, import_paths)
    builder.load_grammar(grammar, source)
    return builder.build()
