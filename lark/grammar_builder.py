"""Grammar builder for Lark.

Contains the GrammarBuilder class, Grammar class, the load_grammar() function,
and related utilities for building and validating Lark grammars.
"""

import hashlib
import os.path
import sys
from collections import namedtuple
from copy import copy, deepcopy
import pkgutil
from contextlib import suppress
from typing import List, Tuple, Union, Callable, Dict, Optional, Sequence

from .utils import bfs, logger, classify_bool, classify, dedup_list, OrderedSet, Serialize
from .lexer import Token, TerminalDef, PatternStr, PatternRE, Pattern
from .grammar import RuleOptions, Rule, Terminal, NonTerminal, Symbol, TOKEN_DEFAULT_PRIORITY
from .exceptions import GrammarError
from .tree import Tree, SlottedTree as ST

# Import from grammar_transforms
from .grammar_transforms import (
    _EMPTY, PrepareLiterals, TerminalTreeToPattern, ApplyTemplates,
    EBNF_to_BNF, PrepareAnonTerminals, SimplifyRule_Visitor,
    RuleTreeToText, ValidateSymbols, nr_deepcopy_tree,
    PrepareGrammar, _find_used_symbols,
)


class Grammar(Serialize):

    term_defs: List[Tuple[str, Tuple[Tree, int]]]
    rule_defs: List[Tuple[str, Tuple[str, ...], Tree, RuleOptions]]
    ignore: List[str]

    def __init__(self, rule_defs: List[Tuple[str, Tuple[str, ...], Tree, RuleOptions]], term_defs: List[Tuple[str, Tuple[Tree, int]]], ignore: List[str]) -> None:
        self.term_defs = term_defs
        self.rule_defs = rule_defs
        self.ignore = ignore

    __serialize_fields__ = 'term_defs', 'rule_defs', 'ignore'

    def compile(self, start, terminals_to_keep) -> Tuple[List[TerminalDef], List[Rule], List[str]]:
        # We change the trees in-place (to support huge grammars)
        # So deepcopy allows calling compile more than once.
        term_defs = [(n, (nr_deepcopy_tree(t), p)) for n, (t, p) in self.term_defs]
        rule_defs = [(n, p, nr_deepcopy_tree(t), o) for n, p, t, o in self.rule_defs]

        # ===================
        #  Compile Terminals
        # ===================

        # Convert terminal-trees to strings/regexps

        for name, (term_tree, priority) in term_defs:
            if term_tree is None:  # Terminal added through %declare
                continue
            if next(term_tree.find_data('template_usage'), None) is not None:
                raise GrammarError("Templates cannot be used inside terminals (%s)" % name)
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
        transformer = PrepareLiterals() * ValidateSymbols() * anon_tokens_transf  # Adds to terminals

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
            res: Tree = ebnf_to_bnf.transform(tree)
            rules.append((name, res, options))
        rules += ebnf_to_bnf.new_rules

        assert len(rules) == len({name for name, _t, _o in rules}), "Whoops, name collision"

        # 4. Compile tree to Rule objects
        rule_tree_to_text = RuleTreeToText()

        simplify_rule = SimplifyRule_Visitor()
        compiled_rules: List[Rule] = []
        for rule_content in rules:
            name, tree, options = rule_content
            simplify_rule.visit(tree)
            expansions = rule_tree_to_text.transform(tree)

            for i, (expansion, alias) in enumerate(expansions):
                if alias and name.startswith('_'):
                    raise GrammarError("Rule %s is marked for expansion (it starts with an underscore) and isn't allowed to have aliases (alias=%s)"% (name, alias))

                empty_indices = tuple(x==_EMPTY for x in expansion)
                if any(empty_indices):
                    exp_options = copy(options) or RuleOptions()
                    exp_options.empty_indices = empty_indices
                    expansion = [x for x in expansion if x!=_EMPTY]
                else:
                    exp_options = options

                for sym in expansion:
                    assert isinstance(sym, Symbol)
                    if sym.is_term and exp_options and exp_options.keep_all_tokens:
                        assert isinstance(sym, Terminal)
                        sym.filter_out = False
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
            compiled_rules = list(OrderedSet(compiled_rules))

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
            terminals, unused = classify_bool(terminals, lambda t: t.name in used_terms or t.name in self.ignore or t.name in terminals_to_keep)
            if unused:
                logger.debug("Unused terminals: %s", [t.name for t in unused])

        return terminals, compiled_rules, self.ignore


PackageResource = namedtuple('PackageResource', 'pkg_name path')


class FromPackageLoader:
    """
    Provides a simple way of creating custom import loaders that load from packages via ``pkgutil.get_data`` instead of using `open`.
    This allows them to be compatible even from within zip files.

    Relative imports are handled, so you can just freely use them.

    pkg_name: The name of the package. You can probably provide `__name__` most of the time
    search_paths: All the path that will be search on absolute imports.
    """

    pkg_name: str
    search_paths: Sequence[str]

    def __init__(self, pkg_name: str, search_paths: Sequence[str]=("", )) -> None:
        self.pkg_name = pkg_name
        self.search_paths = search_paths

    def __repr__(self):
        return "%s(%r, %r)" % (type(self).__name__, self.pkg_name, self.search_paths)

    def __call__(self, base_path: Union[None, str, PackageResource], grammar_path: str) -> Tuple[PackageResource, str]:
        if base_path is None:
            to_try = self.search_paths
        else:
            # Check whether or not the importing grammar was loaded by this module.
            if not isinstance(base_path, PackageResource) or base_path.pkg_name != self.pkg_name:
                # Technically false, but FileNotFound doesn't exist in python2.7, and this message should never reach the end user anyway
                raise IOError()
            to_try = [base_path.path]

        err = None
        for path in to_try:
            full_path = os.path.join(path, grammar_path)
            try:
                text: Optional[bytes] = pkgutil.get_data(self.pkg_name, full_path)
            except IOError as e:
                err = e
                continue
            else:
                return PackageResource(self.pkg_name, full_path), (text.decode() if text else '')

        raise IOError('Cannot find grammar in given paths') from err


def resolve_term_references(term_dict):
    # TODO Solve with transitive closure (maybe)

    while True:
        changed = False
        for name, token_tree in term_dict.items():
            if token_tree is None:  # Terminal added through %declare
                continue
            for exp in token_tree.find_data('value'):
                item ,= exp.children
                if isinstance(item, NonTerminal):
                    raise GrammarError("Rules aren't allowed inside terminals (%s in %s)" % (item, name))
                elif isinstance(item, Terminal):
                    try:
                        term_value = term_dict[item.name]
                    except KeyError:
                        raise GrammarError("Terminal used but not defined: %s" % item.name)
                    assert term_value is not None
                    exp.children[0] = term_value
                    changed = True
                else:
                    assert isinstance(item, Tree)
        if not changed:
            break

    for name, term in term_dict.items():
        if term:    # Not just declared
            for child in term.children:
                ids = [id(x) for x in child.iter_subtrees()]
                if id(term) in ids:
                    raise GrammarError("Recursion in terminal '%s' (recursion is only allowed in rules, not terminals)" % name)



def symbol_from_strcase(s):
    assert isinstance(s, str)
    return Terminal(s, filter_out=s.startswith('_')) if s.isupper() else NonTerminal(s)


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

def _mangle_definition_tree(exp, mangle):
    if mangle is None:
        return exp
    exp = deepcopy(exp) # TODO: is this needed?
    for t in exp.iter_subtrees():
        for i, c in enumerate(t.children):
            if isinstance(c, Symbol):
                t.children[i] = c.renamed(mangle)

    return exp

def _make_rule_tuple(modifiers_tree, name, params, priority_tree, expansions):
    if modifiers_tree.children:
        m ,= modifiers_tree.children
        expand1 = '?' in m
        if expand1 and name.startswith('_'):
            raise GrammarError("Inlined rules (_rule) cannot use the ?rule modifier.")
        keep_all_tokens = '!' in m
    else:
        keep_all_tokens = False
        expand1 = False

    if priority_tree.children:
        p ,= priority_tree.children
        priority = int(p)
    else:
        priority = None

    if params is not None:
        params = [t.value for t in params.children]  # For the grammar parser

    return name, params, expansions, RuleOptions(keep_all_tokens, expand1, priority=priority,
                                                 template_source=(name if params else None))


class Definition:
    def __init__(self, is_term, tree, params=(), options=None):
        self.is_term = is_term
        self.tree = tree
        self.params = tuple(params)
        self.options = options

class GrammarBuilder:

    global_keep_all_tokens: bool
    import_paths: List[Union[str, Callable]]
    used_files: Dict[str, str]

    _definitions: Dict[str, Definition]
    _ignore_names: List[str]

    def __init__(self, global_keep_all_tokens: bool=False, import_paths: Optional[List[Union[str, Callable]]]=None, used_files: Optional[Dict[str, str]]=None) -> None:
        self.global_keep_all_tokens = global_keep_all_tokens
        self.import_paths = import_paths or []
        self.used_files = used_files or {}

        self._definitions: Dict[str, Definition] = {}
        self._ignore_names: List[str] = []

    def _grammar_error(self, is_term, msg, *names):
        args = {}
        for i, name in enumerate(names, start=1):
            postfix = '' if i == 1 else str(i)
            args['name' + postfix] = name
            args['type' + postfix] = lowercase_type = ("rule", "terminal")[is_term]
            args['Type' + postfix] = lowercase_type.title()
        raise GrammarError(msg.format(**args))

    def _check_options(self, is_term, options):
        if is_term:
            if options is None:
                options = 1
            elif not isinstance(options, int):
                raise GrammarError("Terminal require a single int as 'options' (e.g. priority), got %s" % (type(options),))
        else:
            if options is None:
                options = RuleOptions()
            elif not isinstance(options, RuleOptions):
                raise GrammarError("Rules require a RuleOptions instance as 'options'")
            if self.global_keep_all_tokens:
                options.keep_all_tokens = True
        return options


    def _define(self, name, is_term, exp, params=(), options=None, *, override=False):
        if name in self._definitions:
            if not override:
                self._grammar_error(is_term, "{Type} '{name}' defined more than once", name)
        elif override:
            self._grammar_error(is_term, "Cannot override a nonexisting {type} {name}", name)

        if name.startswith('__'):
            self._grammar_error(is_term, 'Names starting with double-underscore are reserved (Error at {name})', name)

        self._definitions[name] = Definition(is_term, exp, params, self._check_options(is_term, options))

    def _extend(self, name, is_term, exp, params=(), options=None):
        if name not in self._definitions:
            self._grammar_error(is_term, "Can't extend {type} {name} as it wasn't defined before", name)

        d = self._definitions[name]

        if is_term != d.is_term:
            self._grammar_error(is_term, "Cannot extend {type} {name} - one is a terminal, while the other is not.", name)
        if tuple(params) != d.params:
            self._grammar_error(is_term, "Cannot extend {type} with different parameters: {name}", name)

        if d.tree is None:
            self._grammar_error(is_term, "Can't extend {type} {name} - it is abstract.", name)

        # TODO: think about what to do with 'options'
        base = d.tree

        assert isinstance(base, Tree) and base.data == 'expansions'
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
                        if isinstance(item, Terminal):
                            # Keep terminal name, no need to create a new definition
                            self._ignore_names.append(item.name)
                            return

            name = '__IGNORE_%d'% len(self._ignore_names)
            self._ignore_names.append(name)
            self._definitions[name] = Definition(True, t, options=TOKEN_DEFAULT_PRIORITY)

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
            name, params, exp, opts = _make_rule_tuple(*tree.children)
            is_term = False
        else:
            name = tree.children[0].value
            params = ()     # TODO terminal templates
            opts = int(tree.children[1]) if len(tree.children) == 3 else TOKEN_DEFAULT_PRIORITY # priority
            exp = tree.children[-1]
            is_term = True

        if mangle is not None:
            params = tuple(mangle(p) for p in params)
            name = mangle(name)

        exp = _mangle_definition_tree(exp, mangle)
        return name, is_term, exp, params, opts


    def load_grammar(self, grammar_text: str, grammar_name: str="<?>", mangle: Optional[Callable[[str], str]]=None) -> None:
        # Import here to avoid circular imports
        from .load_grammar import _parse_grammar

        tree = _parse_grammar(grammar_text, grammar_name)

        imports: Dict[Tuple[str, ...], Tuple[Optional[str], Dict[str, str]]] = {}

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
                for symbol in stmt.children:
                    assert isinstance(symbol, Symbol), symbol
                    is_term = isinstance(symbol, Terminal)
                    if not is_term:
                        raise GrammarError("Expecting terminal name to follow %%declare, but got rule name %r" % symbol.name)
                    if mangle is None:
                        name = symbol.name
                    else:
                        name = mangle(symbol.name)
                    self._define(name, is_term, None)
            elif stmt.data == 'import':
                pass
            else:
                assert False, stmt


        term_defs = { name: d.tree
            for name, d in self._definitions.items()
            if d.is_term
        }
        resolve_term_references(term_defs)


    def _remove_unused(self, used):
        def rule_dependencies(symbol):
            try:
                d = self._definitions[symbol]
            except KeyError:
                return []
            if d.is_term:
                return []
            return _find_used_symbols(d.tree) - set(d.params)

        _used = set(bfs(used, rule_dependencies))
        self._definitions = {k: v for k, v in self._definitions.items() if k in _used}


    def do_import(self, dotted_path: Tuple[str, ...], base_path: Optional[str], aliases: Dict[str, str], base_mangle: Optional[Callable[[str], str]]=None) -> None:
        assert dotted_path
        mangle = _get_mangle('__'.join(dotted_path), aliases, base_mangle)
        grammar_path = os.path.join(*dotted_path) + '.lark'
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
                h = sha256_digest(text)
                if self.used_files.get(joined_path, h) != h:
                    raise RuntimeError("Grammar file was changed during importing")
                self.used_files[joined_path] = h

                gb = GrammarBuilder(self.global_keep_all_tokens, self.import_paths, self.used_files)
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


    def validate(self) -> None:
        for name, d in self._definitions.items():
            params = d.params
            exp = d.tree

            for i, p in enumerate(params):
                if p in self._definitions:
                    raise GrammarError("Template Parameter conflicts with rule %s (in template %s)" % (p, name))
                if p in params[:i]:
                    raise GrammarError("Duplicate Template Parameter %s (in template %s)" % (p, name))

            if exp is None: # Remaining checks don't apply to abstract rules/terminals (created with %declare)
                continue

            for temp in exp.find_data('template_usage'):
                sym = temp.children[0].name
                args = temp.children[1:]
                if sym not in params:
                    if sym not in self._definitions:
                        self._grammar_error(d.is_term, "Template '%s' used but not defined (in {type} {name})" % sym, name)
                    if len(args) != len(self._definitions[sym].params):
                        expected, actual = len(self._definitions[sym].params), len(args)
                        self._grammar_error(d.is_term, "Wrong number of template arguments used for {name} "
                                            "(expected %s, got %s) (in {type2} {name2})" % (expected, actual), sym, name)

            for sym in _find_used_symbols(exp):
                if sym not in self._definitions and sym not in params:
                    self._grammar_error(d.is_term, "{Type} '{name}' used but not defined (in {type2} {name2})", sym, name)

        if not set(self._definitions).issuperset(self._ignore_names):
            raise GrammarError("Terminals %s were marked to ignore but were not defined!" % (set(self._ignore_names) - set(self._definitions)))

    def build(self) -> Grammar:
        self.validate()
        rule_defs = []
        term_defs = []
        for name, d in self._definitions.items():
            (params, exp, options) = d.params, d.tree, d.options
            if d.is_term:
                assert len(params) == 0
                term_defs.append((name, (exp, options)))
            else:
                rule_defs.append((name, params, exp, options))
        # resolve_term_references(term_defs)
        return Grammar(rule_defs, term_defs, self._ignore_names)


def verify_used_files(file_hashes):
    for path, old in file_hashes.items():
        text = None
        if isinstance(path, str) and os.path.exists(path):
            with open(path, encoding='utf8') as f:
                text = f.read()
        elif isinstance(path, PackageResource):
            with suppress(IOError):
                text = pkgutil.get_data(*path).decode('utf-8')
        if text is None: # We don't know how to load the path. ignore it.
            continue

        current = sha256_digest(text)
        if old != current:
            logger.info("File %r changed, rebuilding Parser" % path)
            return False
    return True

def list_grammar_imports(grammar, import_paths=[]):
    "Returns a list of paths to the lark grammars imported by the given grammar (recursively)"
    builder = GrammarBuilder(False, import_paths)
    builder.load_grammar(grammar, '<string>')
    return list(builder.used_files.keys())

def load_grammar(grammar, source, import_paths, global_keep_all_tokens):
    builder = GrammarBuilder(global_keep_all_tokens, import_paths)
    builder.load_grammar(grammar, source)
    return builder.build(), builder.used_files


def sha256_digest(s: str) -> str:
    """Get the sha256 digest of a string

    Supports the `usedforsecurity` argument for Python 3.9+ to allow running on
    a FIPS-enabled system.
    """
    if sys.version_info >= (3, 9):
        return hashlib.sha256(s.encode('utf8'), usedforsecurity=False).hexdigest()
    else:
        return hashlib.sha256(s.encode('utf8')).hexdigest()


IMPORT_PATHS = ['grammars']
stdlib_loader = FromPackageLoader('lark', IMPORT_PATHS)
