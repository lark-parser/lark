"""
 Grammar loader plugin for ABNF grammar (RFC5234 and RFC7405).

 It parses ABNF grammar and creates grammar objects as default grammar loader does.
"""

import sys, os
import hashlib

from lark import Lark, Transformer, Visitor, Tree, Token
from lark import GrammarError, UnexpectedCharacters, UnexpectedToken, ParseError, UnexpectedInput
from typing import List, Tuple, Union, Callable, Dict, Optional
from lark.load_grammar import stdlib_loader, GrammarLoaderBase, PackageResource
from lark.grammar import Terminal, NonTerminal

#inline_args = v_args(inline=True)
ABNF_EXT = '.abnf'

ABNF_GRAMMAR_ERRORS = [
    ('Unexpected line endings', ['a = \n', 'a = ( \n']),
    ('Unclosed parenthesis', ['a = ( x \n']),
    ('Unclosed bracket', ['a = [ x \n']),
    ('Unmatched closing parenthesis', ['a = x )\n', 'a = x ]\n']),
    ('Incorrect type of value', ['a = 1\n']),
    ('Unexpected character (missing "=" or "=/" after rule name, or unusable character in rule name)',
     ['a\n', 'a A\n', 'a /= A\n', 'a == A\n', 'a@rule = x']),
]

def _translate_parser_exception(parse, e):
    error = e.match_examples(parse, ABNF_GRAMMAR_ERRORS, use_accepts=True)
    return error

class ABNFToLarkTransformer(Transformer):
    """ convert parse-tree of ABNF grammar into Lark's EBNF parse-tree. """
    def __init__(self, terminals=(), *args, **kwargs):
        super(ABNFToLarkTransformer, self).__init__(*args, **kwargs)
        self._terminals = terminals

    def char_val(self, items):
        char_val = items[0]
        literal  = char_val.children[0]
        text    = literal[1:-1] # remove double quotes
        if char_val.data == 'case_insensitive_string':
            flags = 'i'
        else:
            flags = ''

        token = literal.update(type_='STRING', value='"{}"{}'.format(text, flags))
        return Tree('value', [ Tree('literal', [token]) ])

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
        #num_val = tree.children[0]
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

        token = num_val.update(type_='REGEXP', value='/{}/'.format(regexp))
        #tree.children = [token]
        #return tree
        return Tree('literal', [token])

    def hex_val(self, items):
        return self._value_range_to_pattern(items[0], base=16)
    def dec_val(self, items):
        return self._value_range_to_pattern(items[0], base=10)
    def bin_val(self, items):
        return self._value_range_to_pattern(items[0], base=2)
    def num_val(self, items):
        return Tree('value', items)

    def concatenation(self, items):
        # rename 'concatenation' in ABNF to 'expansion' in EBNF
        return Tree('expansion', items)

    def alternation(self, items):
        # rename 'alternation' in ABNF to 'expansions' in EBNF
        return Tree('expansions', items)

    def option(self, items):
        # rename to 'expr' and add '?'
        items.append(Token('OP', '?'))
        return Tree('expr', items)

    def rule_ref(self, items):
        # replace hyphens in rule name with underscores
        rulename = items[0].replace('-', '_')
        if rulename in self._terminals:
            return Tree('value', [Terminal(rulename)])
        else:
            return Tree('value', [NonTerminal(rulename)])

    def rule(self, items):
        # remove '=' or '=/'
        assert items[1].type in ('EQ_ALT', 'EQ')
        items.pop(1)

        # replace hyphens in rule name with underscores
        if items[0].find('-') > 0:
            items[0] = items[0].update(value=items[0].replace('-', '_'))

        rulename = items[0].value
        if rulename in self._terminals:
            # rename 'rule' to 'term'
            return Tree('term', items)
        else:
            # insert empty 'template params', 'priority', and rule modifiers
            items[1:1] = [Tree('template_params', []), Tree('priority', [])]
            items.insert(0, Tree('rule_modifiers', []))
            return Tree('rule', items)

    def repetition(self, items):
        """ rewrite repetition in Lark's EBNF form """
        assert len(items) > 0
        if len(items) == 1:
            # no repetition
            return items[0]

        repeat, element = items

        rmin = [ x for x in repeat.find_data('repeat_min') ]
        rmax = [ x for x in repeat.find_data('repeat_max') ]
        rnum = [ x for x in repeat.find_data('repeat_n') ]

        rmin = int(rmin[0].children[0].value) if len(rmin) else 0
        rmax = int(rmax[0].children[0].value) if len(rmax) else None
        rnum = int(rnum[0].children[0].value) if len(rnum) else None

        if rnum is not None:
            # Specific Repetition 'nRule'
            if rnum == 0:
                # generate empty rule
                return Tree('expansion', [] )
            else:
                return Tree('expr', [ element, Token('TILDE', '~'), Token('NUMBER', str(rnum))])

        # Variable Repetition '<a>*<b>Rule', where <a> and <b> are optional
        if rmax is None:
            # '<a>*Rule' or '*Rule'
            if rmin < 0:
                raise GrammarError("Negative repetition is not possible")
            elif rmin == 0:
                # '*Rule' or '0*Rule'
                return Tree('expr', [ element, Token('OP', '*') ])
            else:
                # '<a>*Rule'
                expr1 = Tree('expr', [ element, Token('TILDE', '~'), Token('NUMBER', str(rmin)) ])
                expr2 = Tree('expr', [ element, Token('OP', '*') ])
                # concatenate them
                return Tree('expansion', [expr1, expr2])

        # '*<b>Rule' or '<a>*<b>Rule'
        if rmax < rmin or rmin < 0:
            raise GrammarError("Bad repetition (%d*%d isn't allowed)" % (rmin, rmax))

        if rmin == 0:
            # '*<b>Rule' or '0*<b>Rule'
            expr1 = Tree('expansion', []) # empty
            expr2 = Tree('expansion',
                         [ Tree('expr', [ element, Token('TILDE', '~'),
                                          Token('NUMBER', "1"), Token('NUMBER', str(rmax))])])
            # alternation of them
            tree =Tree('expansions', [expr1, expr2])
        else:
            '<a>*<b>Rule'
            tree = Tree('expr', [ element, Token('TILDE', '~'),
                                  Token('NUMBER', str(rmin)), Token('NUMBER', str(rmax))])
        return tree


class TreeValidator(Visitor):
    def prose_val(self, tree):
        # prose-val is a informal description for humans.
        # we can't generate valid parser if prose-val existed in parse-tree.
        prose = tree.children[0]
        raise GrammarError("This ABNF cannot be used to generate parsers "
                           "since it has prose (informal) descriptions at line %s column %s"
                           % (prose.line, prose.column))



def _find_used_symbols(tree) -> set:
    return {t for x in tree.find_data('rule_ref')
              for t in x.scan_values(lambda t: t.type in ('RULE'))}

def _find_used_symbols_recursive(stmt, rules: Dict[str, Tree]) -> set:
    used_syms = set()

    depends = _find_used_symbols(stmt)
    used_syms.update(depends)
    for sym in used_syms.copy():
        used_syms.update(_find_used_symbols_recursive(rules[sym], rules))

    return used_syms

class ABNFGrammarLoader(GrammarLoaderBase):

    def __init__(self, *args, **kwargs):
        super(ABNFGrammarLoader, self).__init__(*args, **kwargs)

        pkgres_, g = stdlib_loader(None, 'abnf.lark')
        self.parser = Lark(g, parser='earley')


    def _unpack_abnf_import(self, stmt, grammar_name):
        if len(stmt.children) > 1:
            path_node, name_list = stmt.children
            rules_allowlist = {n.value:n.value for n in name_list.children}
        else:
            path_node, = stmt.children
            rules_allowlist = {}

        # '%import topdir.subdir.file' --> dotted_path=('topdir','subdir','file')
        dotted_path = tuple(path_node.children)

        if path_node.data == 'import_from_lib':  # Import from lark/grammars/
            base_path = None
        else:  # Relative import
            if grammar_name == '<string>':
                # Import relative to script file path if grammar is coded in script
                try:
                    base_file = os.path.abspath(sys.modules['__main__'].__file__)
                except AttributeError:
                    base_file = None
            else:
                # Import relative to grammar file path if external grammar file
                base_file = grammar_name
            if base_file:
                if isinstance(base_file, PackageResource):
                    base_path = PackageResource(base_file.pkg_name, os.path.split(base_file.path)[0])
                else:
                    base_path = os.path.split(base_file)[0]
            else:
                base_path = os.path.abspath(os.path.curdir)

        return dotted_path, base_path, rules_allowlist


    def do_import(self, dotted_path: Tuple[str, ...], base_path: Optional[str],
                  allowlist: Dict[str, str]):

        assert dotted_path
        grammar_path = os.path.join(*dotted_path) + ABNF_EXT

        joined_path, text = self.read_grammar_from_file(base_path, grammar_path)

        imported_rules, directives = self._parse_abnf_grammar(text, joined_path)

        rules_to_import = {}
        for rulename, stmt in imported_rules.items():
            # import all rules if allowlist is empty
            if len(allowlist) > 0:
                if rulename not in allowlist:
                    continue
                for sym in _find_used_symbols_recursive(stmt, imported_rules):
                    rules_to_import[sym] = imported_rules[sym]

            rules_to_import[rulename] = stmt

        if len(rules_to_import) == 0:
            raise GrammarError("Nothing was imported from `%s`" % import_path)

        return rules_to_import, directives, grammar_path


    def _parse_abnf_grammar(self, abnf_grammar_text: str, grammar_name:str):

        rules = {}
        casefold_rules = {}

        def add_rule(rulename:str, stmt, grammar_name:str):
            if rulename in rules:
                if stmt.children[1].type != 'EQ_ALT':
                    raise GrammarError("Rule '%s' is already defined in %s"
                                       % (rulename, grammar_name))
                # merge incremental alternation into alternation
                alt      = rules[rulename].children[2]
                alt_incr = stmt.children[2]
                assert alt.data == 'alternation'
                alt.children.extend(alt_incr.children)
            else:
                # case insensitive check for duplicated rule names.
                # (rule names are case insensitive in ABNF.)
                cf_rulename = rulename.casefold()
                try:
                    r = casefold_rules[cf_rulename]
                except KeyError:
                    casefold_rules[cf_rulename] = stmt
                else:
                    raise GrammarError("Rule '%s' is already defined as '%s'"
                                       % (rulename, r.children[0]))

                rules[rulename] = stmt

        try:
            tree = self.parser.parse(abnf_grammar_text)
        except UnexpectedCharacters as e:
            context = e.get_context(abnf_grammar_text)
            error = _translate_parser_exception(self.parser.parse, e)
            if error:
                raise GrammarError("%s, at line %s column %s\n\n%s" % (error, e.line, e.column, context))

            raise GrammarError("Unexpected input at line %d column %d in %s: \n\n%s" %
                               (e.line, e.column, grammar_name, context))
        except UnexpectedToken as e:
            context = e.get_context(text)
            error = _translate_parser_exception(self.parser.parse, e)
            if error:
                raise GrammarError("%s, at line %s column %s\n\n%s" % (error, e.line, e.column, context))
            raise

        imports = {}
        unhandled_directives   = []
        for stmt in tree.children:
            if stmt.data == 'rule':
                rulename = stmt.children[0]
                add_rule(rulename, stmt, grammar_name)

            elif stmt.data == 'abnf_import':
                dotted_path, base_path, allowlist = self._unpack_abnf_import(stmt, grammar_name)
                imported_rules, directives, import_path = self.do_import(dotted_path, base_path, allowlist)

                unhandled_directives.extend(directives)

                for rulename, stmt in imported_rules.items():
                    if rulename in rules:
                        raise GrammarError("Cannot import '%s' from '%s': Symbol already defined."
                                           % (stmt.children[0], import_path))
                    add_rule(rulename, stmt, import_path)

            else:
                unhandled_directives.append(stmt)

        return rules, unhandled_directives


    def parse_grammar(self, abnf_grammar_text: str, grammar_name:str):

        rules, unhandled_directives = self._parse_abnf_grammar(abnf_grammar_text, grammar_name)

        tree = Tree('start', list(rules.values()))

        #======
        # make a list of terminals from %terminal directives
        #======
        terminals = set()
        for stmt in unhandled_directives:
            if stmt.data == 'terminal_def':
                for rulename in stmt.children:
                    terminals.add(rulename.replace('-','_'))
                    if rulename not in rules:
                        raise GrammarError("Symbol '%s' is not defined as a rule, "
                                           "at line %d column %d ." % (rulename, n.line, n.column))
                    terminals.update(_find_used_symbols_recursive(rules[rulename], rules))
            else:
                assert False

        #======
        # Convert ABNF parse tree to Lark's EBNF tree.
        # Note:
        #  - Hyphens in rule names are replaced with underscores.
        #    Otherwise we can't access such rules via visitors and transformers
        #    since hyphen is not a python identifier.
        #
        #  - Rules specified via %terminal directive is converted into terminals.
        #======
        transformer = ABNFToLarkTransformer(terminals)
        tree = transformer.transform(tree)

        #======
        # Error checking
        #======
        validator = TreeValidator()
        validator.visit(tree)

        return tree

def get_grammar_loader(import_paths: Optional[List[Union[str, Callable]]]=None,
                       used_files: Optional[Dict[str, str]]=None):
    """ entry point of this syntax plugin. """
    return ABNFGrammarLoader(import_paths, used_files)
