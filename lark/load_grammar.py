import re
from lexer import Lexer, Token
from grammar_analysis import GrammarAnalyzer
from parser import Parser

from tree import Tree as T, Transformer, Visitor

_TOKEN_NAMES = {
    ':' : 'COLON',
    ',' : 'COMMA',
    ';' : 'SEMICOLON',
    '+' : 'PLUS',
    '-' : 'MINUS',
    '*' : 'STAR',
    '/' : 'SLASH',
    '|' : 'VBAR',
    '!' : 'BANG',
    '?' : 'QMARK',
    '#' : 'HASH',
    '$' : 'DOLLAR',
    '&' : 'AMPERSAND',
    '<' : 'LESSTHAN',
    '>' : 'MORETHAN',
    '=' : 'EQUAL',
    '.' : 'DOT',
    '%' : 'PERCENT',
    '`' : 'BACKQUOTE',
    '^' : 'CIRCUMFLEX',
    '"' : 'DBLQUOTE',
    '\'' : 'QUOTE',
    '~' : 'TILDE',
    '@' : 'AT',
    '(' : 'LPAR',
    ')' : 'RPAR',
    '{' : 'LBRACE',
    '}' : 'RBRACE',
    '[' : 'LSQB',
    ']' : 'RSQB',
}

# Grammar Parser
TOKENS = {
    'LPAR': '\(',
    'RPAR': '\)',
    'LBRA': '\[',
    'RBRA': '\]',
    'OP': '[+*?]',
    'COLON': ':',
    'OR': '\|',
    'DOT': '\.',
    'RULE': '[_?*]?[a-z][_a-z0-9]*',
    'TOKEN': '_?[A-Z][_A-Z0-9]*',
    'STRING': r'".*?[^\\]"',
    'REGEXP': r"/(.|\n)*?[^\\]/",
    'NL': r'(\r?\n)+\s*',
    'WS': r'[ \t]+',
    'COMMENT': r'#[^\n]*\n',
    'TO': '->'
}

RULES = [
    ('start', ['list']),
    ('list', ['item']),
    ('list', ['list', 'item']),
    ('item', ['rule']),
    ('item', ['token']),
    ('item', ['NL']),

    ('rule', ['RULE', 'COLON', 'expansions', 'NL']),
    ('expansions', ['expansion']),
    ('expansions', ['expansions', 'OR', 'expansion']),
    ('expansions', ['expansions', 'NL', 'OR', 'expansion']),

    ('expansion', ['_expansion']),
    ('expansion', ['_expansion', 'TO', 'RULE']),

    ('_expansion', ['expr']),
    ('_expansion', ['_expansion', 'expr']),

    ('expr', ['atom']),
    ('expr', ['atom', 'OP']),

    ('atom', ['LPAR', 'expansions', 'RPAR']),
    ('atom', ['maybe']),

    ('atom', ['RULE']),
    ('atom', ['TOKEN']),
    ('atom', ['anontoken']),

    ('anontoken', ['tokenvalue']),

    ('maybe', ['LBRA', 'expansions', 'RBRA']),

    ('token', ['TOKEN', 'COLON', 'tokenvalue', 'NL']),
    ('token', ['TOKEN', 'tokenmods', 'COLON', 'tokenvalue', 'NL']),
    ('tokenvalue', ['REGEXP']),
    ('tokenvalue', ['STRING']),
    ('tokenmods', ['DOT', 'RULE']),
    ('tokenmods', ['tokenmods', 'DOT', 'RULE']),
]

class SaveDefinitions(object):
    def __init__(self):
        self.rules = {}
        self.tokens = {}
        self.i = 0


    def atom__3(self, _1, value, _2):
        return value
    def atom__1(self, value):
        return value

    def expr__1(self, expr):
        return expr
    def expr(self, *x):
        return T('expr', x)

    def expansion__1(self, expansion):
        return expansion
    def expansion__3(self, expansion, _, alias):
        return T('alias', [expansion, alias])
    def _expansion(self, *x):
        return T('expansion', x)

    def expansions(self, *x):
        items = [i for i in x if isinstance(i, T)]
        return T('expansions', items)

    def maybe(self, _1, expr, _2):
        return T('expr', [expr, Token('OP', '?', -1)])

    def rule(self, name, _1, expansion, _2):
        name = name.value
        if name in self.rules:
            raise ValueError("Rule '%s' defined more than once" % name)

        self.rules[name] = expansion

    def token(self, *x):
        name = x[0].value
        if name in self.tokens:
            raise ValueError("Token '%s' defined more than once" % name)

        if len(x) == 4:
            self.tokens[name] = x[2][1], []
        else:
            self.tokens[name] = x[3][1], x[1].children

    def tokenvalue(self, tokenvalue):
        value = tokenvalue.value[1:-1]
        if tokenvalue.type == 'STRING':
            value = re.escape(value)
        return tokenvalue, value

    def anontoken(self, (token, value)):
        if token.type == 'STRING':
            try:
                token_name = _TOKEN_NAMES[token.value[1:-1]]
            except KeyError:
                if value.isalnum() and value[0].isalpha():
                    token_name = value.upper()
                else:
                    token_name = 'ANONSTR_%d' % self.i
                    self.i += 1
            token_name = '__' + token_name

        elif token.type == 'REGEXP':
            token_name = 'ANONRE_%d' % self.i
            self.i += 1
        else:
            assert False, x

        if token_name not in self.tokens:
            self.tokens[token_name] = value, []

        return Token('TOKEN', token_name, -1)

    def tokenmods__2(self, _, rule):
        return T('tokenmods', [rule.value])
    def tokenmods__3(self, tokenmods, _, rule):
        return T('tokenmods', tokenmods.children + [rule.value])

    def start(self, *x): pass
    def list(self, *x): pass
    def item(self, *x): pass


class EBNF_to_BNF(Transformer):
    def __init__(self):
        self.new_rules = {}
        self.prefix = 'anon'
        self.i = 0

    def _add_recurse_rule(self, type_, expr):
        new_name = '__%s_%s_%d' % (self.prefix, type_, self.i)
        self.i += 1
        t = Token('RULE', new_name, -1)
        self.new_rules[new_name] = T('expansions', [T('expansion', [expr]), T('expansion', [t, expr])])
        return t

    def expr(self, rule, op):
        if op.value == '?':
            return T('expansions', [rule, T('expansion', [])])
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
            return T('expansions', [new_name, T('expansion', [])])
        assert False, op


class SimplifyRule_Visitor(Visitor):

    @staticmethod
    def _flatten(tree):
        while True:
            to_expand = [i for i, child in enumerate(tree.children)
                         if isinstance(child, T) and child.data == tree.data]
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

        while True:
            self._flatten(tree)

            for i, child in enumerate(tree.children):
                if isinstance(child, T) and child.data == 'expansions':
                    tree.data = 'expansions'
                    tree.children = [self.visit(T('expansion', [option if i==j else other
                                                                for j, other in enumerate(tree.children)]))
                                     for option in child.children]
                    break
            else:
                break

    def alias(self, tree):
        rule, alias_name = tree.children
        if rule.data == 'expansions':
            aliases = []
            for child in tree.children[0].children:
                aliases.append(T('alias', [child, alias_name]))
            tree.data = 'expansions'
            tree.children = aliases

    expansions = _flatten

def dict_update_safe(d1, d2):
    for k, v in d2.iteritems():
        assert k not in d1
        d1[k] = v


def generate_aliases():
    sd = SaveDefinitions()
    for name, expansion in RULES:
        try:
            f = getattr(sd, "%s__%s" % (name, len(expansion)))
        except AttributeError:
            f = getattr(sd, name)
        yield name, expansion, f.__name__


def inline_args(f):
    def _f(self, args):
        return f(*args)
    return _f


class GrammarLoader:
    def __init__(self):
        self.rules = list(generate_aliases())
        self.ga = GrammarAnalyzer(self.rules)
        self.ga.analyze()
        self.lexer = Lexer(TOKENS.items(), {}, ignore=['WS', 'COMMENT'])
        self.simplify_rule = SimplifyRule_Visitor()

    def _generate_parser_callbacks(self, callbacks):
        d = {alias: inline_args(getattr(callbacks, alias))
             for _n, _x, alias in self.rules}
        return type('Callback', (), d)()

    def load_grammar(self, grammar_text):
        sd = SaveDefinitions()
        c = self._generate_parser_callbacks(sd)

        p = Parser(self.ga, c)
        p.parse( list(self.lexer.lex(grammar_text+"\n")) )

        ebnf_to_bnf = EBNF_to_BNF()

        rules = {name: ebnf_to_bnf.transform(r) for name, r in sd.rules.items()}
        dict_update_safe(rules, ebnf_to_bnf.new_rules)

        for r in rules.values():
            self.simplify_rule.visit(r)

        return sd.tokens, rules

load_grammar = GrammarLoader().load_grammar


def test():
    g = """
    start: add

    # Rules
    add: mul
       | add _add_sym mul

    mul: _atom
       | mul _add_mul _atom

    neg: "-" _atom

    _atom: neg
         | number
         | "(" add ")"

    # Tokens
    number: /[\d.]+/
    _add_sym: "+" | "-"
    _add_mul: "*" | "/"

    WS.ignore: /\s+/
    """

    g2 = """
    start: a
    a: "a" (b*|(c d)+) "b"?
    b: "b"
    c: "c"
    d: "+" | "-"
    """
    load_grammar(g)



