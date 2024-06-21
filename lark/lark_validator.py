from typing import Any, Dict, List

from .exceptions import GrammarError
from .grammar import TOKEN_DEFAULT_PRIORITY, RuleOptions
from .lexer import Token
from .load_grammar import eval_escaping
from .tree import Tree

class Definition:
    def __init__(self, is_term, tree, params=(), options=None):
        self.is_term = is_term
        self.tree = tree
        self.params = tuple(params)

class LarkValidator:
    """
    Checks a grammar parsed by `lark.lark` for validity using a variety of checks similar to what
    `load_grammar.py` does on parser creation. The only stable public entry point is
    `LarkValidator.validate(tree)`.

    Checks:
    - Illegal constructs not prevented by the grammar:
      - `alias` not in the top expansions of a rule
      - Incorrect `%ignore` lines
      - Invalid literals (like newlines inside of regex without the `x` flag)
      - Rules used inside of Terminals
    - Undefined symbols
    - Incorrectly used templates
    """

    @classmethod
    def validate(cls, tree: Tree, options: Dict[str, Any] = {}):
        """
        Checks a grammar parsed by `lark.lark` for validity using a variety of checks similar to what
        `load_grammar.py` does on parser creation.

        Checks:
        - Illegal constructs not prevented by the grammar:
          - `alias` not in the top expansions of a rule
          - Incorrect `%ignore` lines
          - Invalid literals (like newlines inside of regex without the `x` flag)
          - Rules used inside of Terminals
        - Undefined symbols
        - Incorrectly used templates
        """
        visitor = cls(tree, options)
        visitor._cross_check_symbols()
        visitor._resolve_term_references()
        visitor._check_literals(tree)
        return tree

    def __init__(self, tree: Tree, options: Dict[str, Any]):
        self._definitions: Dict[str, Definition] = {}
        self._ignore_names: List[str] = []
        self._load_grammar(tree)

    def _check_literals(self, tree: Tree) -> None:
        for literal in tree.find_data("literal"):
            self._literal(literal)

    def _cross_check_symbols(self) -> None:
        # Based on load_grammar.GrammarBuilder.validate()
        for name, d in self._definitions.items():
            params = d.params
            definition = d.tree
            for i, p in enumerate(params):
                if p in self._definitions:
                    raise GrammarError("Template Parameter conflicts with rule %s (in template %s)" % (p, name))
                if p in params[:i]:
                    raise GrammarError("Duplicate Template Parameter %s (in template %s)" % (p, name))
            # Remaining checks don't apply to abstract rules/terminals (i.e., created with %declare)
            if definition and isinstance(definition, Tree):
                for template in definition.find_data('template_usage'):
                    if d.is_term:
                        raise GrammarError("Templates not allowed in terminals")
                    sym = template.children[0].data
                    args = template.children[1:]
                    if sym not in params:
                        if sym not in self._definitions:
                            raise GrammarError(f"Template '{sym}' used but not defined (in {('rule', 'terminal')[d.is_term]} {name})")
                        if len(args) != len(self._definitions[sym].params):
                            expected, actual = len(self._definitions[sym].params), len(args)
                            raise GrammarError(f"Wrong number of template arguments used for {expected} "
                                f"(expected {expected}, got {actual}) (in {('rule', 'terminal')[d.is_term]} {actual})")
                for sym in _find_used_symbols(definition):
                    if sym not in self._definitions and sym not in params:
                        raise GrammarError(f"{('Rule', 'Terminal')[sym.isupper()]} '{sym}' used but not defined (in {('rule', 'terminal')[d.is_term]} {    name})")
        if not set(self._definitions).issuperset(self._ignore_names):
            raise GrammarError("Terminals %s were marked to ignore but were not defined!" % (set(self._ignore_names) - set(self._definitions)))

    def _declare(self, stmt: Tree) -> None:
        for symbol in stmt.children:
            if isinstance(symbol, Tree) and symbol.data == 'name':
                symbol = symbol.children[0]
            if not isinstance(symbol, Token) or symbol.type != "TOKEN":
                raise GrammarError("Expecting terminal name")
            self._define(symbol.value, True, None)

    def _define(self, name: str, is_term: bool, exp: "Tree|None", params: List[str] = [], options:Any = None, *, override: bool = False, extend: bool = False) -> None:
        # Based on load_grammar.GrammarBuilder._define()
        if name in self._definitions:
            if not override and not extend:
                raise GrammarError(f"{('Rule', 'Terminal')[is_term]} '{name}' defined more than once")
        if extend:
            base_def = self._definitions[name]
            if is_term != base_def.is_term:
                raise GrammarError("fCannot extend {('rule', 'terminal')[is_term]} {name} - one is a terminal, while the other is not.")
            if tuple(params) != base_def.params:
                raise GrammarError(f"Cannot extend {('rule', 'terminal')[is_term]} with different parameters: {name}")
            if base_def.tree is None:
                raise GrammarError(f"Can't extend {('rule', 'terminal')[is_term]} {name} - it is abstract.")
        if name.startswith('__'):
            raise GrammarError(f'Names starting with double-underscore are reserved (Error at {name})')
        if is_term:
            if options and not isinstance(options, int):
                raise GrammarError(f"Terminal require a single int as 'options' (e.g. priority), got {type(options)}")
        else:
            if options and not isinstance(options, RuleOptions):
                raise GrammarError("Rules require a RuleOptions instance as 'options'")
        self._definitions[name] = Definition(is_term, exp, params)

    def _extend(self, stmt: Tree) -> None:
        definition = stmt.children[0]
        if definition.data == 'token':
            name = definition.children[0]
            if name not in self._definitions:
                raise GrammarError(f"Can't extend terminal {name} as it wasn't defined before")
            self._token(definition, extend=True)
        else:  # definition.data == 'rule'
            name = definition.children[1]
            if name not in self._definitions:
                raise GrammarError(f"Can't extend rule {name} as it wasn't defined before")
            self._rule(definition, extend=True)

    def _ignore(self, stmt: Tree) -> None:
        # Children: expansions
        # - or -
        # Children: token
       exp_or_name = stmt.children[0]
       if isinstance(exp_or_name, str):
            self._ignore_names.append(exp_or_name)
       else:
            assert isinstance(exp_or_name, Tree)
            t = exp_or_name
            if t.data == 'expansions' and len(t.children) == 1:
                t2 ,= t.children
                if t2.data=='expansion':
                    if len(t2.children) > 1:
                        raise GrammarError("Bad %ignore - must have a Terminal or other value.")
                    item ,= t2.children
                    if item.data == 'value':
                        item ,= item.children
                        if isinstance(item, Token):
                            # Keep terminal name, no need to create a new definition
                            self._ignore_names.append(item.value)
                            return
                        if item.data == 'name':
                            token ,= item.children
                            if isinstance(token, Token) and token.type == "TOKEN":
                                # Keep terminal name, no need to create a new definition
                                self._ignore_names.append(token.value)
                                return
            name = '__IGNORE_%d'% len(self._ignore_names)
            self._ignore_names.append(name)
            self._definitions[name] = Definition(True, t, options=TOKEN_DEFAULT_PRIORITY)

    def _literal(self, tree: Tree) -> None:
        # Based on load_grammar.GrammarBuilder.literal_to_pattern().
        assert tree.data == 'literal'
        literal = tree.children[0]
        assert isinstance(literal, Token)
        v = literal.value
        flag_start = max(v.rfind('/'), v.rfind('"'))+1
        assert flag_start > 0
        flags = v[flag_start:]
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

    def _load_grammar(self, tree: Tree) -> None:
        for stmt in tree.children:
            if stmt.data == 'declare':
                self._declare(stmt)
            elif stmt.data == 'extend':
                self._extend(stmt)
            elif stmt.data == 'ignore':
                self._ignore(stmt)
            elif stmt.data in ['import', 'multi_import']:
                # TODO How can we process imports in the validator?
                pass
            elif stmt.data == 'override':
                self._override(stmt)
            elif stmt.data == 'rule':
                self._rule(stmt)
            elif stmt.data == 'token':
                self._token(stmt)
            else:
                assert False, f"Unknown statement type: {stmt}"

    def _override(self, stmt: Tree) -> None:
        definition = stmt.children[0]
        if definition.data == 'token':
            name = definition.children[0]
            if name not in self._definitions:
                raise GrammarError(f"Cannot override a nonexisting terminal {name}")
            self._token(definition, override=True)
        else:  # definition.data == 'rule'
            name = definition.children[1]
            if name not in self._definitions:
                raise GrammarError(f"Cannot override a nonexisting rule {name}")
            self._rule(definition, override=True)

    def _resolve_term_references(self) -> None:
        # Based on load_grammar.resolve_term_references()
        # and the bottom of load_grammar.GrammarBuilder.load_grammar()
        term_dict = { name: d.tree
            for name, d in self._definitions.items()
            if d.is_term
        }
        while True:
            changed = False
            for name, token_tree in term_dict.items():
                if token_tree is None:  # Terminal added through %declare
                    continue
                for exp in token_tree.find_data('value'):
                    item ,= exp.children
                    if isinstance(item, Tree) and item.data == 'name' and isinstance(item.children[0], Token) and item.children[0].type == 'RULE' :
                        raise GrammarError("Rules aren't allowed inside terminals (%s in %s)" % (item, name))
                    elif isinstance(item, Token):
                        try:
                            term_value = term_dict[item.value]
                        except KeyError:
                            raise GrammarError("Terminal used but not defined: %s" % item.value)
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

    def _rule(self, tree, override=False, extend=False) -> None:
        # Children: modifiers, name, params, priority, expansions
        name = tree.children[1]
        if tree.children[0].data == "rule_modifiers" and tree.children[0].children:
            modifiers = tree.children[0].children[0]
            if '?' in modifiers and name.startswith('_'):
                raise GrammarError("Inlined rules (_rule) cannot use the ?rule modifier.")
        if tree.children[2].children[0] is not None:
            params = [t.value for t in tree.children[2].children]  # For the grammar parser
        else:
            params = []
        self._define(name, False, tree.children[4], params=params, override=override, extend=extend)

    def _token(self, tree, override=False, extend=False) -> None:
        # Children: name, priority, expansions
        # - or -
        # Children: name, expansions
        if tree.children[1].data == "priority" and tree.children[1].children:
            opts = int(tree.children[1].children[0])  # priority
        else:
            opts = TOKEN_DEFAULT_PRIORITY
        for item in tree.children[-1].find_data('alias'):
            raise GrammarError("Aliasing not allowed in terminals (You used -> in the wrong place)")
        self._define(tree.children[0].value, True, tree.children[-1], [], opts, override=override, extend=extend)

def _find_used_symbols(tree) -> List[str]:
    # Based on load_grammar.GrammarBuilder._find_used_symbols()
    assert tree.data == 'expansions'
    results = []
    for expansion in tree.find_data('expansion'):
        for item in expansion.scan_values(lambda t: True):
            if isinstance(item, Tree) and item.data == 'name':
                results.append(item.data)
            elif isinstance(item, Token) and item.type not in ['NUMBER', 'OP', 'STRING', 'REGEXP']:
                results.append(item.value)
    return results
