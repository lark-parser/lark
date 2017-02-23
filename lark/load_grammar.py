import os.path
from itertools import chain
import re
import codecs

from .lexer import Lexer, Token, UnexpectedInput, TokenDef__Str, TokenDef__Regexp

from .parse_tree_builder import ParseTreeBuilder
from .parser_frontends import LALR
from .parsers.lalr_parser import UnexpectedToken
from .common import is_terminal, GrammarError, LexerConf, ParserConf

from .tree import Tree as T, Transformer, InlineTransformer, Visitor

unicode_escape = codecs.getdecoder('unicode_escape')

__path__ = os.path.dirname(__file__)
IMPORT_PATHS = [os.path.join(__path__, 'grammars')]


_TOKEN_NAMES = {
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
TOKENS = {
    '_LPAR': r'\(',
    '_RPAR': r'\)',
    '_LBRA': r'\[',
    '_RBRA': r'\]',
    'OP': '[+*?](?![a-z])',
    '_COLON': ':',
    '_OR': r'\|',
    '_DOT': r'\.',
    'RULE': '!?[_?]?[a-z][_a-z0-9]*',
    'TOKEN': '_?[A-Z][_A-Z0-9]*',
    'STRING': r'".*?[^\\]"',
    'REGEXP': r"/(?!/).*?[^\\]/",
    '_NL': r'(\r?\n)+\s*',
    'WS': r'[ \t]+',
    'COMMENT': r'//[^\n]*',
    '_TO': '->',
    '_IGNORE': r'%ignore',
    '_IMPORT': r'%import',
}

RULES = {
    'start': ['_list'],
    '_list':  ['_item', '_list _item'],
    '_item':  ['rule', 'token', 'statement', '_NL'],

    'rule': ['RULE _COLON expansions _NL'],
    'expansions': ['alias',
                   'expansions _OR alias',
                   'expansions _NL _OR alias'],

    '?alias':     ['expansion _TO RULE', 'expansion'],
    'expansion': ['_expansion'],

    '_expansion': ['', '_expansion expr'],

    '?expr': ['atom',
              'atom OP'],

    '?atom': ['_LPAR expansions _RPAR',
             'maybe',
             'name',
             'tokenvalue',
             'range'],

    '?name': ['RULE', 'TOKEN'],

    'maybe': ['_LBRA expansions _RBRA'],
    'range': ['STRING _DOT _DOT STRING'],

    'token': ['TOKEN _COLON expansions _NL'],
    'statement': ['ignore', 'import'],
    'ignore': ['_IGNORE expansions _NL'],
    'import': ['_IMPORT import_args _NL',
               '_IMPORT import_args _TO TOKEN'],
    'import_args': ['_import_args'],
    '_import_args': ['name', '_import_args _DOT name'],

    'tokenvalue': ['REGEXP', 'STRING'],
}


class EBNF_to_BNF(InlineTransformer):
    def __init__(self):
        self.new_rules = {}
        self.rules_by_expr = {}
        self.prefix = 'anon'
        self.i = 0

    def _add_recurse_rule(self, type_, expr):
        if expr in self.rules_by_expr:
            return self.rules_by_expr[expr]

        new_name = '__%s_%s_%d' % (self.prefix, type_, self.i)
        self.i += 1
        t = Token('RULE', new_name, -1)
        self.new_rules[new_name] = T('expansions', [T('expansion', [expr]), T('expansion', [t, expr])])
        self.rules_by_expr[expr] = t
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
    for k, v in d2.items():
        assert k not in d1
        d1[k] = v


class RuleTreeToText(Transformer):
    def expansions(self, x):
        return x
    def expansion(self, symbols):
        return [sym.value for sym in symbols], None
    def alias(self, x):
        (expansion, _alias), alias = x
        assert _alias is None, (alias, expansion, '-', _alias)
        return expansion, alias.value


class SimplifyTree(InlineTransformer):
    def maybe(self, expr):
        return T('expr', [expr, Token('OP', '?', -1)])

    def tokenmods(self, *args):
        if len(args) == 1:
            return list(args)
        tokenmods, value = args
        return tokenmods + [value]

class ExtractAnonTokens(InlineTransformer):
    def __init__(self, tokens, token_set):
        self.tokens = tokens
        self.token_set = token_set
        self.token_reverse = {td.value: td.name for td in tokens}
        self.i = 0

    def tokenvalue(self, token):
        if token.type == 'STRING':
            value = token.value[1:-1]
            try:
                # If already defined, use the user-defined token name
                token_name = self.token_reverse[value]
            except KeyError:
                # Try to assign an indicative anon-token name, otherwise use a numbered name
                try:
                    token_name = _TOKEN_NAMES[value]
                except KeyError:
                    if value.isalnum() and value[0].isalpha() and ('__'+value.upper()) not in self.token_set:
                        token_name = value.upper()  # This can create name duplications for unidentical tokens
                    else:
                        token_name = 'ANONSTR_%d' % self.i
                        self.i += 1
                token_name = '__' + token_name

        elif token.type == 'REGEXP':
            token_name = 'ANONRE_%d' % self.i
            value = token.value
            self.i += 1
        else:
            assert False, token

        if value in self.token_reverse: # Kind of a wierd placement
            token_name = self.token_reverse[value]

        if token_name not in self.token_set:
            self.token_set.add(token_name)
            if token.type == 'STRING':
                self.tokens.append(TokenDef__Str(token_name, token[1:-1]))
            else:
                self.tokens.append(TokenDef__Regexp(token_name, token[1:-1]))
            assert value not in self.token_reverse, value
            self.token_reverse[value] = token_name

        return Token('TOKEN', token_name, -1)


class TokenValue(object):
    def __init__(self, value):
        self.value = value

class TokenValue__Str(TokenValue):
    def to_regexp(self):
        return re.escape(self.value)

class TokenValue__Regexp(TokenValue):
    def to_regexp(self):
        return self.value

class TokenTreeToRegexp(Transformer):
    def tokenvalue(self, tv):
        tv ,= tv
        value = tv.value[1:-1]

        if r'\u' in value:
            # XXX for now, you can't mix unicode escaping and unicode characters at the same token
            value = unicode_escape(value)[0]

        if tv.type == 'REGEXP':
            return TokenValue__Regexp(value)
        elif tv.type == 'STRING':
            return TokenValue__Str(value)

        assert False

    def expansion(self, items):
        if len(items) == 1:
            return items[0]
        return TokenValue__Regexp(''.join(i.to_regexp() for i in items))
    def expansions(self, exps):
        if len(exps) == 1:
            return exps[0]
        return TokenValue__Regexp('(?:%s)' % ('|'.join(i.to_regexp() for i in exps)))
    def range(self, items):
        assert all(i.type=='STRING' for i in items)
        items = [i[1:-1] for i in items]
        start, end = items
        assert len(start) == len(end) == 1, (start, end)
        return TokenValue__Regexp('[%s-%s]' % (start, end))

    def expr(self, args):
        inner, op = args
        return TokenValue__Regexp('(?:%s)%s' % (inner.to_regexp(), op))

class Grammar:
    def __init__(self, rule_defs, token_defs, extra):
        self.token_defs = token_defs
        self.rule_defs = rule_defs
        self.extra = extra

    def compile(self, lexer=False):
        assert lexer

        tokendefs = list(self.token_defs)

        # =================
        #  Compile Tokens
        # =================
        token_to_regexp = TokenTreeToRegexp()

        # Convert tokens to strings/regexps
        tokens = []
        for name, token_tree in tokendefs:
            regexp = token_to_regexp.transform(token_tree)
            if isinstance(regexp, TokenValue__Str):
                tokendef = TokenDef__Str(name, regexp.value)
            else:
                tokendef = TokenDef__Regexp(name, regexp.to_regexp())
            tokens.append(tokendef)

        #  Resolve regexp assignments of the form /..${X}../
        # XXX This is deprecated, since you can express most regexps with EBNF
        # XXX Also, since this happens after import, it can be a source of bugs
        token_dict = {td.name: td.to_regexp() for td in tokens}
        while True:
            changed = False
            for t in tokens:
                if isinstance(t, TokenDef__Regexp):
                    sp = re.split(r'(\$\{%s})' % TOKENS['TOKEN'], t.value)
                    if sp:
                        value = ''.join(token_dict[x[2:-1]] if x.startswith('${') and x.endswith('}') else x
                                        for x in sp)
                        if value != t.value:
                            t.value = value
                            changed = True
            if not changed:
                break

        # =================
        #  Compile Rules
        # =================
        extract_anon = ExtractAnonTokens(tokens, set(token_dict))
        ebnf_to_bnf = EBNF_to_BNF()
        simplify_rule = SimplifyRule_Visitor()
        rule_tree_to_text = RuleTreeToText()
        rules = {}

        for name, rule_tree in self.rule_defs:
            assert name not in rules
            tree = extract_anon.transform(rule_tree) # Adds to tokens
            rules[name] = ebnf_to_bnf.transform(tree)

        dict_update_safe(rules, ebnf_to_bnf.new_rules)

        for r in rules.values():
            simplify_rule.visit(r)

        rules = {origin: rule_tree_to_text.transform(tree) for origin, tree in rules.items()}

        return tokens, rules, self.extra



class GrammarRule:
    def __init__(self, name, expansions):
        self.keep_all_tokens = name.startswith('!')
        name = name.lstrip('!')
        self.expand1 = name.startswith('?')
        name = name.lstrip('?')

        self.name = name
        self.expansions = expansions



_imported_grammars = {}
def import_grammar(grammar_path):
    if grammar_path not in _imported_grammars:
        for import_path in IMPORT_PATHS:
            with open(os.path.join(import_path, grammar_path)) as f:
                text = f.read()
            grammar = load_grammar(text)
            _imported_grammars[grammar_path] = grammar

    return _imported_grammars[grammar_path]


def resolve_token_references(token_defs):
    token_dict = dict(token_defs)
    assert len(token_dict) == len(token_defs), "Same name defined twice?"

    while True:
        changed = False
        for name, token_tree in token_defs:
            for exp in chain(token_tree.find_data('expansion'), token_tree.find_data('expr')):
                for i, item in enumerate(exp.children):
                    if isinstance(item, Token):
                        if item.type == 'RULE':
                            raise GrammarError("Rules aren't allowed inside tokens (%s in %s)" % (item, name))
                        if item.type == 'TOKEN':
                            exp.children[i] = token_dict[item]
                            changed = True
        if not changed:
            break


class GrammarLoader:
    def __init__(self):
        tokens = [TokenDef__Regexp(name, value) for name, value in TOKENS.items()]

        d = {r: [(x.split(), None) for x in xs] for r, xs in RULES.items()}
        rules, callback = ParseTreeBuilder(T).create_tree_builder(d, None)
        lexer_conf = LexerConf(tokens, ['WS', 'COMMENT'], None)
        parser_conf = ParserConf(rules, callback, 'start')
        self.parser = LALR(lexer_conf, parser_conf)

        self.simplify_tree = SimplifyTree()

    def load_grammar(self, grammar_text):
        try:
            tree = self.simplify_tree.transform( self.parser.parse(grammar_text+'\n') )
        except UnexpectedInput as e:
            raise GrammarError("Unexpected input %r at line %d column %d" % (e.context, e.line, e.column))
        except UnexpectedToken as e:
            if '_COLON' in e.expected:
                raise GrammarError("Missing colon at line %s column %s" % (e.line, e.column))
            elif 'tokenvalue' in e.expected:
                raise GrammarError("Expecting a value at line %s column %s" % (e.line, e.column))
            elif e.expected == ['_OR']:
                raise GrammarError("Newline without starting a new option (Expecting '|') at line %s column %s" % (e.line, e.column))
            raise

        # Extract grammar items

        token_defs = [c.children for c in tree.children if c.data=='token']
        rule_defs = [c.children for c in tree.children if c.data=='rule']
        statements = [c.children for c in tree.children if c.data=='statement']
        assert len(token_defs) + len(rule_defs) + len(statements) == len(tree.children)

        token_defs = [(name.value, t) for name, t in token_defs]

        # Execute statements
        ignore = []
        for (stmt,) in statements:
            if stmt.data == 'ignore':
                expansions ,= stmt.children
                ignore.append(expansions)
            elif stmt.data == 'import':
                dotted_path = stmt.children[0].children
                name = stmt.children[1] if len(stmt.children)>1 else dotted_path[-1]
                grammar_path = os.path.join(*dotted_path[:-1]) + '.g'
                g = import_grammar(grammar_path)
                token_tree = dict(g.token_defs)[dotted_path[-1]]
                token_defs.append([name.value, token_tree])
            else:
                assert False, command


        # Verify correctness 1
        for name, _ in token_defs:
            if name.startswith('__'):
                raise GrammarError('Names starting with double-underscore are reserved (Error at %s)' % name)
        # Handle ignore tokens
        ignore_names = []
        for i, t in enumerate(ignore):
            if t.data == 'expansions' and len(t.children) == 1:
                x ,= t.children
                if x.data == 'expansion' and len(x.children) == 1:
                    item ,= x.children
                    if isinstance(item, Token) and item.type == 'TOKEN':
                        # XXX is this really a wise solution? -- Erez
                        ignore_names.append(item.value)
                        continue

            name = '__IGNORE_%d'%i
            token_defs.append((name, t))
            ignore_names.append(name)

        # Resolve token references
        resolve_token_references(token_defs)

        # Verify correctness 2
        token_names = set()
        for name, _ in token_defs:
            if name in token_names:
                raise GrammarError("Token '%s' defined more than once" % name)
            token_names.add(name)

        rules = [GrammarRule(name, x) for name, x in rule_defs]

        rule_names = set()
        for r in rules:
            if r.name.startswith('__'):
                raise GrammarError('Names starting with double-underscore are reserved (Error at %s)' % name)
            if r.name in rule_names:
                raise GrammarError("Rule '%s' defined more than once" % r.name)
            rule_names.add(r.name)

        for r in rules:
            used_symbols = {t for x in r.expansions.find_data('expansion')
                              for t in x.scan_values(lambda t: t.type in ('RULE', 'TOKEN'))}
            for sym in used_symbols:
                if is_terminal(sym):
                    if sym not in token_names:
                        raise GrammarError("Token '%s' used but not defined (in rule %s)" % (sym, r.name))
                else:
                    if sym not in rule_names:
                        raise GrammarError("Rule '%s' used but not defined (in rule %s)" % (sym, r.name))

        # TODO don't include unused tokens, they can only cause trouble!

        return Grammar(rule_defs, token_defs, {'ignore': ignore_names})



load_grammar = GrammarLoader().load_grammar
