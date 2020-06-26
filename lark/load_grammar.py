"Parses and creates Grammar objects"

import os.path
import sys
from copy import copy, deepcopy
from io import open

from .utils import bfs, eval_escaping
from .lexer import Token, TerminalDef, PatternStr, PatternRE

from .parse_tree_builder import ParseTreeBuilder
from .parser_frontends import LALR_TraditionalLexer
from .common import LexerConf, ParserConf
from .grammar import RuleOptions, Rule, Terminal, NonTerminal, Symbol
from .utils import classify, suppress, dedup_list, Str
from .exceptions import GrammarError, UnexpectedCharacters, UnexpectedToken

from .tree import Tree, SlottedTree as ST
from .visitors import Transformer, Visitor, v_args, Transformer_InPlace, Transformer_NonRecursive
inline_args = v_args(inline=True)

__path__ = os.path.dirname(__file__)
IMPORT_PATHS = [os.path.join(__path__, 'grammars')]

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
    'REGEXP': r'/(?!/)(\\/|\\\\|[^/\n])*?/[%s]*' % _RE_FLAGS,
    '_NL': r'(\r?\n)+\s*',
    'WS': r'[ \t]+',
    'COMMENT': r'\s*//[^\n]*',
    '_TO': '->',
    '_IGNORE': r'%ignore',
    '_DECLARE': r'%declare',
    '_IMPORT': r'%import',
    'NUMBER': r'[+-]?\d+',
}

RULES = {
    'start': ['_list'],
    '_list':  ['_item', '_list _item'],
    '_item':  ['rule', 'term', 'statement', '_NL'],

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
    'statement': ['ignore', 'import', 'declare'],
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
                tree.children = [self.visit(ST('expansion', [option if i==j else other
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


@inline_args
class CanonizeTree(Transformer_InPlace):
    def tokenmods(self, *args):
        if len(args) == 1:
            return list(args)
        tokenmods, value = args
        return tokenmods + [value]

class PrepareAnonTerminals(Transformer_InPlace):
    "Create a unique list of anonymous terminals. Attempt to give meaningful names to them when we add them"

    def __init__(self, terminals):
        self.terminals = terminals
        self.term_set = {td.name for td in self.terminals}
        self.term_reverse = {td.pattern: td for td in terminals}
        self.i = 0


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
                    if value.isalnum() and value[0].isalpha() and value.upper() not in self.term_set:
                        with suppress(UnicodeEncodeError):
                            value.upper().encode('ascii') # Make sure we don't have unicode in our terminal names
                            term_name = value.upper()

                if term_name in self.term_set:
                    term_name = None

        elif isinstance(p, PatternRE):
            if p in self.term_reverse: # Kind of a wierd placement.name
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

        return Terminal(term_name, filter_out=isinstance(p, PatternStr))

class _ReplaceSymbols(Transformer_InPlace):
    " Helper for ApplyTemplates "

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
    " Apply the templates, creating new rules that represent the used templates "

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




def _literal_to_pattern(literal):
    v = literal.value
    flag_start = _rfind(v, '/"')+1
    assert flag_start > 0
    flags = v[flag_start:]
    assert all(f in _RE_FLAGS for f in flags), flags

    v = v[:flag_start]
    assert v[0] == v[-1] and v[0] in '"/'
    x = v[1:-1]

    s = eval_escaping(x)

    if literal.type == 'STRING':
        s = s.replace('\\\\', '\\')

    return { 'STRING': PatternStr,
             'REGEXP': PatternRE }[literal.type](s, flags)


@inline_args
class PrepareLiterals(Transformer_InPlace):
    def literal(self, literal):
        return ST('pattern', [_literal_to_pattern(literal)])

    def range(self, start, end):
        assert start.type == end.type == 'STRING'
        start = start.value[1:-1]
        end = end.value[1:-1]
        assert len(eval_escaping(start)) == len(eval_escaping(end)) == 1, (start, end, len(eval_escaping(start)), len(eval_escaping(end)))
        regexp = '[%s-%s]' % (start, end)
        return ST('pattern', [PatternRE(regexp)])


class TerminalTreeToPattern(Transformer):
    def pattern(self, ps):
        p ,= ps
        return p

    def expansion(self, items):
        assert items
        if len(items) == 1:
            return items[0]
        if len({i.flags for i in items}) > 1:
            raise GrammarError("Lark doesn't support joining terminals with conflicting flags!")
        return PatternRE(''.join(i.to_regexp() for i in items), items[0].flags if items else ())

    def expansions(self, exps):
        if len(exps) == 1:
            return exps[0]
        if len({i.flags for i in exps}) > 1:
            raise GrammarError("Lark doesn't support joining terminals with conflicting flags!")
        return PatternRE('(?:%s)' % ('|'.join(i.to_regexp() for i in exps)), exps[0].flags)

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

def _choice_of_rules(rules):
    return ST('expansions', [ST('expansion', [Token('RULE', name)]) for name in rules])

def nr_deepcopy_tree(t):
    "Deepcopy tree `t` without recursion"
    return Transformer_NonRecursive(False).transform(t)

class Grammar:
    def __init__(self, rule_defs, term_defs, ignore):
        self.term_defs = term_defs
        self.rule_defs = rule_defs
        self.ignore = ignore

    def compile(self, start):
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
        terminals = [TerminalDef(name, transformer.transform( term_tree ), priority)
                     for name, (term_tree, priority) in term_defs if term_tree]

        # =================
        #  Compile Rules
        # =================

        # 1. Pre-process terminals
        transformer = PrepareLiterals() * PrepareSymbols() * PrepareAnonTerminals(terminals)  # Adds to terminals

        # 2. Inline Templates

        transformer *= ApplyTemplates(rule_defs)

        # 3. Convert EBNF to BNF (and apply step 1 & 2)
        ebnf_to_bnf = EBNF_to_BNF()
        rules = []
        i = 0
        while i < len(rule_defs): # We have to do it like this because rule_defs might grow due to templates
            name, params, rule_tree, options = rule_defs[i]
            i += 1
            if len(params) != 0: # Dont transform templates
                continue
            ebnf_to_bnf.rule_options = RuleOptions(keep_all_tokens=True) if options.keep_all_tokens else None
            ebnf_to_bnf.prefix = name
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
                    raise GrammarError("Rule %s is marked for expansion (it starts with an underscore) and isn't allowed to have aliases (alias=%s)" % (name, alias))

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
            compiled_rules = [r for r in compiled_rules if r.origin in used_rules]
            if len(compiled_rules) == c:
                break

        # Filter out unused terminals
        used_terms = {t.name for r in compiled_rules
                             for t in r.expansion
                             if isinstance(t, Terminal)}
        terminals = [t for t in terminals if t.name in used_terms or t.name in self.ignore]

        return terminals, compiled_rules, self.ignore



_imported_grammars = {}
def import_grammar(grammar_path, re_, base_paths=[]):
    if grammar_path not in _imported_grammars:
        import_paths = base_paths + IMPORT_PATHS
        for import_path in import_paths:
            with suppress(IOError):
                joined_path = os.path.join(import_path, grammar_path)
                with open(joined_path, encoding='utf8') as f:
                    text = f.read()
                grammar = load_grammar(text, joined_path, re_)
                _imported_grammars[grammar_path] = grammar
                break
        else:
            open(grammar_path, encoding='utf8')
            assert False

    return _imported_grammars[grammar_path]

def import_from_grammar_into_namespace(grammar, namespace, aliases):
    """Returns all rules and terminals of grammar, prepended
    with a 'namespace' prefix, except for those which are aliased.
    """

    imported_terms = dict(grammar.term_defs)
    imported_rules = {n:(n,p,deepcopy(t),o) for n,p,t,o in grammar.rule_defs}

    term_defs = []
    rule_defs = []

    def rule_dependencies(symbol):
        if symbol.type != 'RULE':
            return []
        try:
            _, params, tree,_ = imported_rules[symbol]
        except KeyError:
            raise GrammarError("Missing symbol '%s' in grammar %s" % (symbol, namespace))
        return _find_used_symbols(tree) - set(params)



    def get_namespace_name(name, params):
        if params is not None:
            try:
                return params[name]
            except KeyError:
                pass
        try:
            return aliases[name].value
        except KeyError:
            if name[0] == '_':
                return '_%s__%s' % (namespace, name[1:])
            return '%s__%s' % (namespace, name)

    to_import = list(bfs(aliases, rule_dependencies))
    for symbol in to_import:
        if symbol.type == 'TERMINAL':
            term_defs.append([get_namespace_name(symbol, None), imported_terms[symbol]])
        else:
            assert symbol.type == 'RULE'
            _, params, tree, options = imported_rules[symbol]
            params_map = {p: ('%s__%s' if p[0]!='_' else '_%s__%s' ) % (namespace, p) for p in params}
            for t in tree.iter_subtrees():
                for i, c in enumerate(t.children):
                    if isinstance(c, Token) and c.type in ('RULE', 'TERMINAL'):
                        t.children[i] = Token(c.type, get_namespace_name(c, params_map))
            params = [params_map[p] for p in params] # We can not rely on ordered dictionaries
            rule_defs.append((get_namespace_name(symbol, params_map), params, tree, options))


    return term_defs, rule_defs



def resolve_term_references(term_defs):
    # TODO Solve with transitive closure (maybe)

    term_dict = {k:t for k, (t,_p) in term_defs}
    assert len(term_dict) == len(term_defs), "Same name defined twice?"

    while True:
        changed = False
        for name, (token_tree, _p) in term_defs:
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
    params = [t.value for t in params.children] if params is not None else [] # For the grammar parser

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

class GrammarLoader:
    def __init__(self, re_):
        self.re = re_
        terminals = [TerminalDef(name, PatternRE(value)) for name, value in TERMINALS.items()]

        rules = [options_from_rule(name, None, x) for name, x in  RULES.items()]
        rules = [Rule(NonTerminal(r), symbols_from_strcase(x.split()), i, None, o) for r, _p, xs, o in rules for i, x in enumerate(xs)]
        callback = ParseTreeBuilder(rules, ST).create_callback()
        lexer_conf = LexerConf(terminals, ['WS', 'COMMENT'])

        parser_conf = ParserConf(rules, callback, ['start'])
        self.parser = LALR_TraditionalLexer(lexer_conf, parser_conf, re_)

        self.canonize_tree = CanonizeTree()

    def load_grammar(self, grammar_text, grammar_name='<?>'):
        "Parse grammar_text, verify, and create Grammar object. Display nice messages on error."

        try:
            tree = self.canonize_tree.transform( self.parser.parse(grammar_text+'\n') )
        except UnexpectedCharacters as e:
            context = e.get_context(grammar_text)
            raise GrammarError("Unexpected input at line %d column %d in %s: \n\n%s" %
                               (e.line, e.column, grammar_name, context))
        except UnexpectedToken as e:
            context = e.get_context(grammar_text)
            error = e.match_examples(self.parser.parse, {
                'Unclosed parenthesis': ['a: (\n'],
                'Umatched closing parenthesis': ['a: )\n', 'a: [)\n', 'a: (]\n'],
                'Expecting rule or terminal definition (missing colon)': ['a\n', 'a->\n', 'A->\n', 'a A\n'],
                'Alias expects lowercase name': ['a: -> "a"\n'],
                'Unexpected colon': ['a::\n', 'a: b:\n', 'a: B:\n', 'a: "a":\n'],
                'Misplaced operator': ['a: b??', 'a: b(?)', 'a:+\n', 'a:?\n', 'a:*\n', 'a:|*\n'],
                'Expecting option ("|") or a new rule or terminal definition': ['a:a\n()\n'],
                '%import expects a name': ['%import "a"\n'],
                '%ignore expects a value': ['%ignore %import\n'],
            })
            if error:
                raise GrammarError("%s at line %s column %s\n\n%s" % (error, e.line, e.column, context))
            elif 'STRING' in e.expected:
                raise GrammarError("Expecting a value at line %s column %s\n\n%s" % (e.line, e.column, context))
            raise

        tree = PrepareGrammar().transform(tree)

        # Extract grammar items
        defs = classify(tree.children, lambda c: c.data, lambda c: c.children)
        term_defs = defs.pop('term', [])
        rule_defs = defs.pop('rule', [])
        statements = defs.pop('statement', [])
        assert not defs

        term_defs = [td if len(td)==3 else (td[0], 1, td[1]) for td in term_defs]
        term_defs = [(name.value, (t, int(p))) for name, p, t in term_defs]
        rule_defs = [options_from_rule(*x) for x in rule_defs]

        # Execute statements
        ignore, imports = [], {}
        for (stmt,) in statements:
            if stmt.data == 'ignore':
                t ,= stmt.children
                ignore.append(t)
            elif stmt.data == 'import':
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
                    name = path_node.children[-1]  # Get name from dotted path
                    aliases = {name: arg1 or name}  # Aliases if exist

                if path_node.data == 'import_lib':  # Import from library
                    base_paths = []
                else:  # Relative import
                    if grammar_name == '<string>':  # Import relative to script file path if grammar is coded in script
                        try:
                            base_file = os.path.abspath(sys.modules['__main__'].__file__)
                        except AttributeError:
                            base_file = None
                    else:
                        base_file = grammar_name  # Import relative to grammar file path if external grammar file
                    if base_file:
                        base_paths = [os.path.split(base_file)[0]]
                    else:
                        base_paths = [os.path.abspath(os.path.curdir)]

                try:
                    import_base_paths, import_aliases = imports[dotted_path]
                    assert base_paths == import_base_paths, 'Inconsistent base_paths for %s.' % '.'.join(dotted_path)
                    import_aliases.update(aliases)
                except KeyError:
                    imports[dotted_path] = base_paths, aliases

            elif stmt.data == 'declare':
                for t in stmt.children:
                    term_defs.append([t.value, (None, None)])
            else:
                assert False, stmt

        # import grammars
        for dotted_path, (base_paths, aliases) in imports.items():
            grammar_path = os.path.join(*dotted_path) + EXT
            g = import_grammar(grammar_path, self.re, base_paths=base_paths)
            new_td, new_rd = import_from_grammar_into_namespace(g, '__'.join(dotted_path), aliases)

            term_defs += new_td
            rule_defs += new_rd

        # Verify correctness 1
        for name, _ in term_defs:
            if name.startswith('__'):
                raise GrammarError('Names starting with double-underscore are reserved (Error at %s)' % name)

        # Handle ignore tokens
        # XXX A slightly hacky solution. Recognition of %ignore TERMINAL as separate comes from the lexer's
        #     inability to handle duplicate terminals (two names, one value)
        ignore_names = []
        for t in ignore:
            if t.data=='expansions' and len(t.children) == 1:
                t2 ,= t.children
                if t2.data=='expansion' and len(t2.children) == 1:
                    item ,= t2.children
                    if item.data == 'value':
                        item ,= item.children
                        if isinstance(item, Token) and item.type == 'TERMINAL':
                            ignore_names.append(item.value)
                            continue

            name = '__IGNORE_%d'% len(ignore_names)
            ignore_names.append(name)
            term_defs.append((name, (t, 1)))

        # Verify correctness 2
        terminal_names = set()
        for name, _ in term_defs:
            if name in terminal_names:
                raise GrammarError("Terminal '%s' defined more than once" % name)
            terminal_names.add(name)

        if set(ignore_names) > terminal_names:
            raise GrammarError("Terminals %s were marked to ignore but were not defined!" % (set(ignore_names) - terminal_names))

        resolve_term_references(term_defs)

        rules = rule_defs

        rule_names = {}
        for name, params, _x, _o in rules:
            if name.startswith('__'):
                raise GrammarError('Names starting with double-underscore are reserved (Error at %s)' % name)
            if name in rule_names:
                raise GrammarError("Rule '%s' defined more than once" % name)
            rule_names[name] = len(params)

        for name, params , expansions, _o in rules:
            for i, p in enumerate(params):
                if p in rule_names:
                    raise GrammarError("Template Parameter conflicts with rule %s (in template %s)" % (p, name))
                if p in params[:i]:
                    raise GrammarError("Duplicate Template Parameter %s (in template %s)" % (p, name))
            for temp in expansions.find_data('template_usage'):
                sym = temp.children[0]
                args = temp.children[1:]
                if sym not in params:
                    if sym not in rule_names:
                        raise GrammarError("Template '%s' used but not defined (in rule %s)" % (sym, name))
                    if len(args) != rule_names[sym]:
                        raise GrammarError("Wrong number of template arguments used for %s "
                                           "(expected %s, got %s) (in rule %s)"%(sym, rule_names[sym], len(args), name))
            for sym in _find_used_symbols(expansions):
                if sym.type == 'TERMINAL':
                    if sym not in terminal_names:
                        raise GrammarError("Token '%s' used but not defined (in rule %s)" % (sym, name))
                else:
                    if sym not in rule_names and sym not in params:
                        raise GrammarError("Rule '%s' used but not defined (in rule %s)" % (sym, name))


        return Grammar(rules, term_defs, ignore_names)



def load_grammar(grammar, source, re_):
    return GrammarLoader(re_).load_grammar(grammar, source)
