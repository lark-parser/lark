"""Parses grammar written in ABNF (RFC5234 and 7405) and creates Grammar objects. """
import hashlib
import os, sys

from .load_grammar import PrepareGrammar, PrepareAnonTerminals
from .load_grammar import EBNF_to_BNF, SimplifyRule_Visitor
from .load_grammar import _get_parser, symbols_from_strcase, nr_deepcopy_tree
from .load_grammar import PackageResource, stdlib_loader

from .utils import logger
from .lexer import Token, TerminalDef, Pattern, PatternRE, PatternStr

from .parse_tree_builder import ParseTreeBuilder
from .parser_frontends import ParsingFrontend
from .common import LexerConf, ParserConf
from .grammar import RuleOptions, Rule, Terminal, NonTerminal, Symbol, TOKEN_DEFAULT_PRIORITY
from .tree import Tree, SlottedTree as ST
from .utils import classify, classify_bool, bfs
from .exceptions import GrammarError, UnexpectedCharacters, UnexpectedToken

from .visitors import v_args, Transformer_InPlace, Transformer_NonRecursive, Visitor, Transformer
inline_args = v_args(inline=True)

_ALL_RULES = object()
ABNF_EXT = '.abnf'

# Terminals (ie. keys in TERMINALS ) shall consist of uppercase letters and underscores.
TERMINALS = {
    '_LPAR':     r'\(',
    '_RPAR':     r'\)',
    '_LBRA':     r'\[',
    '_RBRA':     r'\]',
    '_STAR'  :     r'\*',
    '_SLASH' :     r'/',

    'RULENAME':     r'[a-zA-Z][a-zA-Z0-9\-]*',
    'EQ':          r'=',
    'EQ_ALT':      r'=/',

    '_IGNORE_CASE':    r'%i',
    '_CASE_SENSITIVE': r'%s',

    # quoted-string  =  DQUOTE *(%x20-21 / %x23-7E) DQUOTE
    'QSTRING':      r'"[ !#$%&\'\(\)\*\+,\-\./0-9:;<=>\?@A-Z\[\\\]\^_a-z\{|\}~]*"',

    # prose-val = "<" *(%x20-3D / %x3F-7E) ">"
    'PROSE_VAL' :   r'<[ !"#$%&\'\(\)\*\+,\-\./0-9:;<=\?@A-Z\[\\\]\^_a-z\{|\}~]*>',

    'NUMBER'     :  r'[0-9]+',

    'DEC_VAL':      r'%d([0-9]+(\.[0-9]+)+|[0-9]+\-[0-9]+|[0-9]+)',
    'HEX_VAL':      r'%x([0-9A-F]+(\.[0-9A-F]+)+|[0-9A-F]+\-[0-9A-F]+|[0-9A-F]+)',
    'BIN_VAL':      r'%b([01]+(\.[01]+)+|[01]+\-[01]+|[01]+)',

    # c-wsp = WSP / (c-nl WSP)
    'C_WSP':       r'[ \t]+|((;[^\n]*)*\r?\n)[ \t]+',
    '_C_NL':       r'((;[^\n]*)*\r?\n)(?![ \t])',

    # terminals for nonstandard extensions
    '_IMPORT': r'%import',
    '_DOT':  r'\.',
    '_COMMA':  r',',

    # define terminal for unusable charaters to see nice error messages for common pitfalls
    '_UNUSABLE_CHARS': r'[_@!#$&\+:]'
}
_TERMINALS_TO_IGNORE=['C_WSP']


# Name of rules (ie. keys in RULES below) shall consist of lowercase letters and underscores.
RULES = {
    'start':         ['_rulelist'],

    # rulelist       =  1*( rule / (*c-wsp c-nl) )
    '_rulelist':     ['_item', '_rulelist _item'],
    '_item':         ['rule', 'import', '_C_NL' ], # 'import' is nonstandard extension

    # There are some assumptions in rule for 'rule'
    #
    # - Name of the rule definition shall be 'rule'
    # - First element in the lefthand side of the rule shall be named as 'RULENAME'
    # - '_c-nl' cannot be renamed to 'c-nl',
    #   otherwise self._unpack_definition() will fail to capture 'elements'
    #
    'rule':          ['RULENAME _defined_as elements _C_NL'],

    '_defined_as':    [ 'EQ', 'EQ_ALT' ],

    # elements       =  alternation *c-wsp
    # alternation    =  concatenation *(*c-wsp "/" *c-wsp concatenation)
    # concatenation  =  repetition *(1*c-wsp repetition)
    # repetition     =  [repeat] element
    #
    'elements':      [ 'alternation' ],
    'alternation':   [ '_alternation'],
    '_alternation':  [ 'concatenation', '_alternation _SLASH concatenation'],
    'concatenation': [ '_concatenation'],
    '_concatenation':[ 'repetition', '_concatenation repetition'],

    'repetition':    [ 'element', 'repeat element' ],

    # repeat         =  1*DIGIT / (*DIGIT "*" *DIGIT)
    'repeat':        [ 'repeat_min _STAR repeat_max',
                       'repeat_min _STAR',
                       '_STAR repeat_max',
                       '_STAR',
                       'repeat_n' ],

    'repeat_n':      [ 'NUMBER' ],
    'repeat_min':    [ 'NUMBER' ],
    'repeat_max':    [ 'NUMBER' ],

    'element':       [ 'RULENAME', '_group', 'option', 'char_val', 'num_val', 'prose_val'],

    # 'group' is inlined intentionally.
    #
    # grouping will produces nested 'alternation' rule tree.
    #   (e.g.  '"a" | ("b")' in ABNF produces 'alternation("a", alternation("b"))' in AST terms.)
    #
    # Such nested and redundant rule will be flattened later
    # by SimplifyRule_Visitor()._flatten().
    '_group':         [ '_LPAR alternation _RPAR' ],
    'option':        [ '_LBRA alternation _RBRA' ],

    'char_val':      [ 'case_insensitive_string', 'case_sensitive_string' ],
    'case_insensitive_string': [ '_IGNORE_CASE    QSTRING', 'QSTRING' ],
    'case_sensitive_string':   [ '_CASE_SENSITIVE QSTRING' ],

    'num_val':       [ 'dec_val', 'bin_val', 'hex_val',],

    'dec_val':       [ 'DEC_VAL' ],
    'hex_val':       [ 'HEX_VAL' ],
    'bin_val':       [ 'BIN_VAL' ],

    'prose_val':     [ 'PROSE_VAL' ],

    # nonstandard extensions to ABNF grammar (%import directive)
    'import': ['_IMPORT _import_path _C_NL',
               '_IMPORT _import_path _LPAR name_list _RPAR _C_NL',
    ],
    '_import_path':    ['import_from_lib', 'import_relpath'],
    'import_from_lib': ['_import_args'],
    'import_relpath':  ['_DOT _import_args'],
    '_import_args':    ['RULENAME', '_import_args _DOT RULENAME'],

    'name_list': ['_name_list'],
    '_name_list': ['RULENAME', '_name_list _COMMA RULENAME'],
}


class ABNF_to_BNF(EBNF_to_BNF):
    """ converts ABNF to BNF.
    we reuse super()._add_repeat_rule() etc. from EBNF_to_BNF via inheritance.
    """

    def _add_recurse_rule(self, type_, element, repeat_min):
        assert repeat_min >= 1

        new_name = self._name_rule(type_)
        t = NonTerminal(new_name)
        tree = ST('alternation', [
            ST('concatenation', [element] * repeat_min),
            ST('concatenation', [t, element])
        ])
        return self._add_rule(element, new_name, tree)

    def option(self, items):
        assert len(items) == 1

        # RFC5234 Section 3.8: Optional Sequence:  [RULE]
        empty = ST('concatenation', [])
        alternation = items[0]
        return  ST('alternation', [alternation, empty])

    def repetition(self, items):
        if len(items) == 1:
            # no repetition
            return items[0]

        repeat  = items[0]
        element = items[1]

        rmin = [ x for x in repeat.find_data('repeat_min') ]
        rmax = [ x for x in repeat.find_data('repeat_max') ]
        rnum = [ x for x in repeat.find_data('repeat_n') ]

        rmin = int(rmin[0].children[0].value) if len(rmin) else 0
        rmax = int(rmax[0].children[0].value) if len(rmax) else None
        rnum = int(rnum[0].children[0].value) if len(rnum) else None

        if rnum is not None:
            # Specific Repetition 'nRule'
            if rnum == 0:
                empty = ST('concatenation', [])
                return  ST('alternation', [empty])

            else:
                rmin = rmax = rnum
        else:
            # Variable Repetition '<a>*<b>Rule', where <a> and <b> are optional
            if rmax is None:
                if rmin == 0:
                    # '*Rule' (or '0*Rule')
                    new_name = self._add_recurse_rule('star', element, 1)
                    empty    = ST('concatenation',  [])
                    return ST('alternation', [new_name, empty])
                else:
                    # '<a>*Rule'
                    return self._add_recurse_rule('repeat_min', element, rmin)

            else:
                # '*<b>Rule' or '<a>*<b>Rule'
                pass

        if rmax < rmin or rmin < 0:
            raise GrammarError("Bad repetition (%d*%d isn't allowed)" % (rmin, rmax))

        return self._generate_repeats(element, rmin, rmax)

class RenameRule_Visitor(Visitor):
    """ rename ABNF Rule names to EBNF ones to reuse SimplifyRule_Visitor(). """
    def concatenation(self, tree):
        tree.data = 'expansion'

    def alternation(self, tree):
        tree.data = 'expansions'


class ABNFRuleTreeToText(Transformer):

    def expansion(self, symbols):
        # renamed from 'concatenation'
        return symbols

    def expansions(self, x):
        # renamed from 'alternation'
        return x

    def elements(self, x):
        return x[0]

    def prose_val(self, x):
        prose = x[0]
        raise GrammarError("This ABNF cannot be used to generate parsers "
                           "since it has prose (informal) descriptions at line %s column %s"
                           % (prose.line, prose.column))


@inline_args
class PrepareLiterals(Transformer_InPlace):
    """ convert literals (char-val and num-val tokens in ABNF) into regexps """
    def char_val(self, char_val):
        literal = char_val.children[0].value
        text    = literal[1:-1] # remove double quotes
        if char_val.data == 'case_insensitive_string':
            flags = ('i')
        else:
            flags = ()

        return ST('pattern', [PatternStr(text, flags=flags, raw=literal)])

    def _char_to_pattern(self, num_val_literal, base):
        char = int(num_val_literal, base=base)
        if char > 0xffffffff:
            raise GrammarError("Terminal value characters larger than 0xffffffff is not supported.")
        elif char > 0xffff:
            regexp = r'\U{:08x}'.format(char)
        elif char > 0xff:
            regexp = r'\u{:04x}'.format(char)
        else:
            regexp = r'\x{:02x}'.format(char)
        return regexp

    def _value_range_to_pattern(self, num_val, base=10):
        literal = num_val.value[2:]
        if literal.find('.') > 0:
            # '.' concatenation of values
            nums = ( self._char_to_pattern(num, base) for num in literal.split('.') )
            regexp = ''.join(nums)

        elif literal.find('-') > 0:
            # '-' value range
            start, end = ( self._char_to_pattern(num, base) for num in literal.split('-') )
            regexp = r'[%s-%s]' % (start, end)
        else:
            regexp = self._char_to_pattern(literal, base)

        # list is unpacked in self.num_val()
        return [ ST('pattern', [PatternRE(regexp)]) ]

    def hex_val(self, literal):
        return self._value_range_to_pattern(literal, base=16)
    def dec_val(self, literal):
        return self._value_range_to_pattern(literal, base=10)
    def bin_val(self, literal):
        return self._value_range_to_pattern(literal, base=2)

    def num_val(self, items):
        return items[0]


class PruneTerminalTreeToPattern(Transformer_NonRecursive):
    """
    simplify terminal-tree by converting it into single instance of PatternRE or PatternStr,
    which is created by PrepareLiterals().transform().
    """
    def pattern(self, ps):
        p ,= ps
        return p;

    def elements(self, items):
        assert len(items) == 1
        return items[0]

    def alternation(self, items):
        assert len(items) == 1
        return items[0]

    def concatenation(self, items):
        assert len(items) == 1
        return items[0]

    def repetition(self, items):
        assert len(items) == 1
        return items[0]

    def element(self, items):
        assert len(items) == 1
        return items[0]

    def num_val(self, items):
        assert len(items) == 1 and isinstance(items[0], Pattern)
        return items[0]

class PrepareRuleNames(Transformer_InPlace):
    def __init__(self, rule_names):
        self.rule_names = rule_names

    def element(self, v):
        v ,= v
        if isinstance(v, Tree):
            return v

        assert isinstance(v, Token)
        if v.type == 'RULENAME':
            if v.value in self.rule_names:
                return NonTerminal(str(v.value))

            return Terminal(str(v.value))

        assert False


class ABNFGrammar:
    def __init__(self, rule_defs, term_defs, ignore):
        self.term_defs = term_defs
        self.rule_defs = rule_defs
        self.ignore = ignore

    def compile(self, start, terminals_to_keep):
        # We change the trees in-place (to support huge grammars)
        # So deepcopy allows calling compile more than once.
        term_defs = [(n, (nr_deepcopy_tree(t), p)) for n, (t, p) in self.term_defs]
        rule_defs = [(n, nr_deepcopy_tree(t), o) for n, t, o in self.rule_defs]

        # ===================
        #  Compile Terminals
        # ===================

        # This transformer applies PrepareLiterals first.
        # It converts literals to regexps and place them in instances of PatternRE or PatternStr.
        #
        # Next, PruneTerminalTreeToPattern is applied to simplify terminal-tree to
        # single instance of PatternRE or PatternStr.

        transformer = PrepareLiterals() * PruneTerminalTreeToPattern()

        terminal_list = [TerminalDef(name, transformer.transform(term_tree), priority)
                         for name, (term_tree, priority) in term_defs if term_tree]

        # =================
        #  Compile Rules
        # =================

        # convert literals in rule_defs to Terminals, rule names to NonTerminals.
        rule_names  = [n for n, _t, _o in self.rule_defs]
        transformer = PrepareLiterals() * PrepareRuleNames(rule_names)

        # convert anonymous terminals (i.e. literals in the right-hand-side of ABNF rules)
        # to terminals and add them to terminal_list

        anon_tokens_transf = PrepareAnonTerminals(terminal_list)
        transformer *= anon_tokens_transf

        # Convert ABNF to BNF. It will convert as follows:
        #  - repetitions (e.g. 1*DIGIT) ->  recursive rules or repetition of symbols,
        #  - optional sequences (e.g. [ "word" ] ) -> alternation (e.g. ' "word" | "" ' )

        abnf_to_bnf = ABNF_to_BNF()

        rules = []
        for name, rule_tree, options in rule_defs:
            rule_options = RuleOptions(keep_all_tokens=True) if options and options.keep_all_tokens else None
            abnf_to_bnf.rule_options = rule_options
            abnf_to_bnf.prefix       = name
            tree = transformer.transform(rule_tree)
            res  = abnf_to_bnf.transform(tree)
            rules.append((name, res, options))

        # add recursive rules generated in abnf_to_bnf.transform()
        rules += abnf_to_bnf.new_rules

        # Compile tree to Rule objects

        # rename ABNF rule names to EBNF ones to reuse SimplifyRule_Visitor()
        #  ('alternation' in ABNF -> 'expansions',  'concatenation' in ABNF -> 'expansion' )
        rename_rule       = RenameRule_Visitor()

        # unpack some rule trees and simplify nested rule tree in expansion and expansions
        simplify_rule     = SimplifyRule_Visitor()

        # unpack Tree objects to list of symbols
        rule_tree_to_text = ABNFRuleTreeToText()

        compiled_rules = []
        for rule_content in rules:
            name, tree, options = rule_content

            rename_rule.visit(tree)
            simplify_rule.visit(tree)

            expansions = rule_tree_to_text.transform(tree)

            for i, expansion in enumerate(expansions):

                alias       = None
                exp_options = options
                rule = Rule(NonTerminal(name), expansion, i, alias, exp_options)
                compiled_rules.append(rule)

        # assertion will fail if there are duplicates of rules
        assert len(set(compiled_rules)) == len(compiled_rules)

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
        if terminals_to_keep != '*':
            used_terms = {t.name for r in compiled_rules
                                 for t in r.expansion
                                 if isinstance(t, Terminal)}
            terminal_list, unused = classify_bool(terminal_list, lambda t: t.name in used_terms or t.name in self.ignore or t.name in terminals_to_keep)
            if unused:
                logger.debug("Unused terminals: %s", [t.name for t in unused])

        return terminal_list, compiled_rules, self.ignore



def _find_used_symbols(tree):
    assert tree.data == 'elements'
    return {t for x in tree.find_data('element')
              for t in x.scan_values(lambda t: t.type in ('RULENAME'))}

def _get_abnf_parser():
    try:
        return _get_abnf_parser.cache
    except AttributeError:
        terminals = [TerminalDef(name, PatternRE(value)) for name, value in TERMINALS.items()]

        rules = [(rulename, exp, RuleOptions()) for rulename, exp in RULES.items()]

        rules = [Rule(NonTerminal(rulename), symbols_from_strcase(x.split()), i, None, o)
                 for rulename, elements, o in rules for i, x in enumerate(elements)]

        callback = ParseTreeBuilder(rules, ST).create_callback()
        import re
        lexer_conf = LexerConf(terminals, re, _TERMINALS_TO_IGNORE)
        parser_conf = ParserConf(rules, callback, ['start'])
        lexer_conf.lexer_type = 'basic'
        parser_conf.parser_type = 'lalr'
        _get_abnf_parser.cache = ParsingFrontend(lexer_conf, parser_conf, None)
        return _get_abnf_parser.cache

ABNF_GRAMMAR_ERRORS = [
    ('Unclosed parenthesis', ['a = ( \n']),
    ('Unclosed bracket', ['a = [ \n']),
    ('Incorrect type of value', ['a = 1\n']),
    ('Unmatched closing parenthesis', ['a = )\n', 'a = ]\n', 'a = [)\n', 'a = (]\n']),
    ('Expecting rule or terminal definition (missing "=" or "=/")',
     ['a\n', 'a A\n', 'a /= A\n', 'a == A\n']),
    ('Unexpected character, which is not usable in ABNF grammar', ['a@rule = "a rule"\n']),
]

def _translate_parser_exception(parse, e):
    error = e.match_examples(parse, ABNF_GRAMMAR_ERRORS, use_accepts=True)
    if error:
        return error
    elif 'STRING' in e.expected:
        return "Expecting a value"

def _parse_abnf_grammar(text, name, start='start'):
    try:
        tree = _get_abnf_parser().parse(text + '\n', start)
    except UnexpectedCharacters as e:
        context = e.get_context(text)
        raise GrammarError("Unexpected input at line %d column %d in %s: \n\n%s" %
                           (e.line, e.column, name, context))
    except UnexpectedToken as e:
        context = e.get_context(text)
        error = _translate_parser_exception(_get_abnf_parser().parse, e)
        if error:
            raise GrammarError("%s, at line %s column %s\n\n%s" % (error, e.line, e.column, context))
        raise

    return PrepareGrammar().transform(tree)

class ABNFGrammarBuilder:
    def __init__(self, global_keep_all_tokens=False, import_paths=None, used_files=None):
        self.global_keep_all_tokens = global_keep_all_tokens
        self.import_paths = import_paths or []
        self.used_files = used_files or {}

        self._definitions = {}
        self._ignore_names = []

    def _is_terminal(self, tree):
        if not isinstance(tree, Tree):
            # it would be a token (RULENAME). it is non-terminal.
            return False

        # It is a terminal if rule reduces to single instance of char-val or num-val.
        if len(tree.children) > 1:
            return False
        elif len(tree.children) == 1:
            if tree.data in ('char_val', 'num_val'):
                return True
            else:
                return self._is_terminal(tree.children[0])

        assert False, tree

    def _remove_unused(self, used):
        def rule_dependencies(symbol):
            try:
                tree = self._definitions[symbol]
            except KeyError:
                return []
            return _find_used_symbols(tree)

        _used = set(bfs(used, rule_dependencies))
        self._definitions = {k: v for k, v in self._definitions.items() if k in _used}

    def _define(self, name, oper, exp):
        if name in self._definitions:
            if oper == '=/':

                assert isinstance(exp.children[0].children[0], Tree)
                assert exp.children[0].children[0].data == 'concatenation'

                # unify incremental alternatives into existing alternatives
                base_exp = self._definitions[name]
                base_exp.children[0].children += exp.children[0].children
                return

            raise GrammarError("Rule '%s' defined more than once" % name)

        if name.startswith('__'):
            raise GrammarError("Names starting with double-underscore are reserved (Error at '%s'})" % name)

        self._definitions[name] = exp

    def _unpack_definition(self, tree):
        assert tree.data == 'rule'
        rulename = tree.children[0].value
        oper     = tree.children[1].value  # '=' or '=/'
        rule_elements = tree.children[-1]

        assert isinstance(rule_elements, Tree) and rule_elements.data == 'elements'

        return rulename, oper, rule_elements


    def _unpack_import(self, stmt, grammar_name):
        if len(stmt.children) > 1:
            path_node, name_list = stmt.children
            rules_to_import = [n.value for n in name_list.children]
        else:
            path_node, = stmt.children
            rules_to_import = _ALL_RULES

        # '%import topdir.subdir.file' --> dotted_path=['topdir','subdir','file']
        dotted_path = tuple(path_node.children)

        if path_node.data == 'import_from_lib':  # Import from lark/grammars/
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

        return dotted_path, base_path, rules_to_import

    def do_import(self, dotted_path, base_path, rules_to_import):

        assert dotted_path
        grammar_path = os.path.join(*dotted_path) + ABNF_EXT

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
                h = hashlib.md5(text.encode('utf8')).hexdigest()
                if self.used_files.get(joined_path, h) != h:
                    raise RuntimeError("Grammar file was changed during importing")
                self.used_files[joined_path] = h

                gb = ABNFGrammarBuilder(self.global_keep_all_tokens, self.import_paths, self.used_files)
                gb.load_grammar(text, joined_path)
                if rules_to_import != _ALL_RULES:
                    gb._remove_unused(rules_to_import)

                for name in gb._definitions:
                    if name in self._definitions:
                        raise GrammarError("Cannot import '%s' from '%s': Symbol already defined." % (name, grammar_path))

                self._definitions.update(**gb._definitions)
                break
        else:
            # Search failed. Make Python throw a nice error.
            open(grammar_path, encoding='utf8')
            assert False, "Couldn't import grammar %s, but a corresponding file was found at a place where lark doesn't search for it" % (dotted_path,)

    def load_grammar(self, grammar_text, grammar_name="<?>"):
        tree = _parse_abnf_grammar(grammar_text, grammar_name)

        imports = {}
        for stmt in tree.children:
            if stmt.data == 'import':
                dotted_path, base_path, rules_to_import = self._unpack_import(stmt, grammar_name)
                try:
                    import_base_path, import_rules = imports[dotted_path]
                    assert base_path == import_base_path, 'Inconsistent base_path for %s.' % '.'.join(dotted_path)
                    import_rules.update(rules_to_import)
                except KeyError:
                    imports[dotted_path] = base_path, rules_to_import

        for dotted_path, (base_path, rules_to_import) in imports.items():
            self.do_import(dotted_path, base_path, rules_to_import)

        for stmt in tree.children:
            if stmt.data == 'rule':
                self._define(*self._unpack_definition(stmt))
            elif stmt.data == 'import':
                pass
            else:
                assert False, stmt

    def validate(self):
        for name, elements in self._definitions.items():
            for sym in _find_used_symbols(elements):
                if sym not in self._definitions:
                    raise GrammarError("Rule '%s' used but not defined in %s" % (sym, name))

    def build(self):
        rule_defs = []
        term_defs = []
        prio      = TOKEN_DEFAULT_PRIORITY
        for name, exp in self._definitions.items():
            if self._is_terminal(exp):
                options = prio
                term_defs.append((name, (exp, options)))
            else:
                options = RuleOptions(keep_all_tokens=self.global_keep_all_tokens,
                                      expand1=False, priority=prio, template_source=None)
                rule_defs.append((name, exp, options))

        return ABNFGrammar(rule_defs, term_defs, self._ignore_names)


def load_abnf_grammar(grammar, source, import_paths, global_keep_all_tokens):
    builder = ABNFGrammarBuilder(global_keep_all_tokens, import_paths)
    builder.load_grammar(grammar, source)
    builder.validate()
    return builder.build(), builder.used_files
