"""Parses and compiles Lark grammars into an internal representation.

This module contains the grammar DSL parser (TERMINALS, RULES, _get_parser,
_parse_grammar) and error handling utilities. The GrammarBuilder and
transformer classes have been extracted to grammar_builder.py and
grammar_transforms.py respectively.
"""

import hashlib
import os.path
import sys
from collections import namedtuple
from copy import copy, deepcopy
import pkgutil
from ast import literal_eval
from contextlib import suppress
from typing import List, Tuple, Union, Callable, Dict, Optional, Sequence, Generator

from .utils import bfs, logger, classify_bool, is_id_continue, is_id_start, bfs_all_unique, small_factors, OrderedSet, Serialize
from .lexer import Token, TerminalDef, PatternStr, PatternRE, Pattern

from .parse_tree_builder import ParseTreeBuilder
from .parser_frontends import ParsingFrontend
from .common import LexerConf, ParserConf
from .grammar import RuleOptions, Rule, Terminal, NonTerminal, Symbol, TOKEN_DEFAULT_PRIORITY
from .utils import classify, dedup_list
from .exceptions import GrammarError, UnexpectedCharacters, UnexpectedToken, ParseError, UnexpectedInput

from .tree import Tree, SlottedTree as ST
from .visitors import Transformer, Visitor, v_args, Transformer_InPlace, Transformer_NonRecursive
inline_args = v_args(inline=True)

# Re-export from new modules for backward compatibility
from .grammar_builder import (
    Grammar, FromPackageLoader, PackageResource, GrammarBuilder,
    verify_used_files, load_grammar, list_grammar_imports, sha256_digest,
    resolve_term_references, symbol_from_strcase, stdlib_loader,
)
from .grammar_transforms import (
    _EMPTY, _TERMINAL_NAMES, SMALL_FACTOR_THRESHOLD, REPEAT_BREAK_THRESHOLD,
    FindRuleSize, EBNF_to_BNF, SimplifyRule_Visitor, RuleTreeToText,
    PrepareAnonTerminals, _ReplaceSymbols, ApplyTemplates,
    PrepareLiterals, TerminalTreeToPattern, ValidateSymbols,
    nr_deepcopy_tree, PrepareGrammar, _find_used_symbols,
    eval_escaping, _literal_to_pattern, _make_joined_pattern,
    _rfind,
)

EXT = '.lark'
IMPORT_PATHS = ['grammars']

_RE_FLAGS = 'imslux'


# Grammar Parser
TERMINALS = {
    '_LPAR': r'\(',
    '_RPAR': r'\)',
    '_LBRA': r'\[',
    '_RBRA': r'\]',
    '_LBRACE': r'\{',
    '_RBRACE': r'\}',
    'OP': '[+*]|[?](?![a-z_])',
    '_COLON': ':',
    '_COMMA': ',',
    '_OR': r'\|',
    '_DOT': r'\.(?!\.)',
    '_DOTDOT': r'\.\.',
    'TILDE': '~',
    'RULE_MODIFIERS': '(!|![?]?|[?]!?)(?=[_a-z])',
    'RULE': '_?[a-z][_a-z0-9]*',
    'TERMINAL': '_?[A-Z][_A-Z0-9]*',
    'STRING': r'"(\\"|\\\\|[^"\n])*?"i?',
    'REGEXP': r'/(?!/)(\\/|\\\\|[^/])*?/[%s]*' % _RE_FLAGS,
    '_NL': r'(\r?\n)+\s*',
    '_NL_OR': r'(\r?\n)+\s*\|',
    'WS': r'[ \t]+',
    'COMMENT': r'\s*//[^\n]*|\s*#[^\n]*',
    'BACKSLASH': r'\\[ ]*\n',
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

    'rule': ['rule_modifiers RULE template_params priority _COLON expansions _NL'],
    'rule_modifiers': ['RULE_MODIFIERS',
                       ''],
    'priority': ['_DOT NUMBER',
                 ''],
    'template_params': ['_LBRACE _template_params _RBRACE',
                        ''],
    '_template_params': ['RULE',
                         '_template_params _COMMA RULE'],
    'expansions': ['_expansions'],
    '_expansions': ['alias',
                    '_expansions _OR alias',
                    '_expansions _NL_OR alias'],

    '?alias':     ['expansion _TO nonterminal', 'expansion'],
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
    '?symbol': ['terminal', 'nonterminal'],

    'maybe': ['_LBRA expansions _RBRA'],
    'range': ['STRING _DOTDOT STRING'],

    'template_usage': ['nonterminal _LBRACE _template_args _RBRACE'],
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

    '_declare_args': ['symbol', '_declare_args symbol'],
    'literal': ['REGEXP', 'STRING'],
}


def _get_parser():
    try:
        return _get_parser.cache
    except AttributeError:
        terminals = [TerminalDef(name, PatternRE(value)) for name, value in TERMINALS.items()]

        rules = [(name.lstrip('?'), x, RuleOptions(expand1=name.startswith('?')))
                for name, x in RULES.items()]
        rules = [Rule(NonTerminal(r), [symbol_from_strcase(s) for s in x.split()], i, None, o)
                 for r, xs, o in rules for i, x in enumerate(xs)]

        callback = ParseTreeBuilder(rules, ST).create_callback()
        import re
        lexer_conf = LexerConf(terminals, re, ['WS', 'COMMENT', 'BACKSLASH'])
        parser_conf = ParserConf(rules, callback, ['start'])
        lexer_conf.lexer_type = 'basic'
        parser_conf.parser_type = 'lalr'
        _get_parser.cache = ParsingFrontend(lexer_conf, parser_conf, None)
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

def _error_repr(error):
    if isinstance(error, UnexpectedToken):
        error2 = _translate_parser_exception(_get_parser().parse, error)
        if error2:
            return error2
        expected = ', '.join(error.accepts or error.expected)
        return "Unexpected token %r. Expected one of: {%s}" % (str(error.token), expected)
    else:
        return str(error)

def _search_interactive_parser(interactive_parser, predicate):
    def expand(node):
        path, p = node
        for choice in p.choices():
            t = Token(choice, '')
            try:
                new_p = p.feed_token(t)
            except ParseError:    # Illegal
                pass
            else:
                yield path + (choice,), new_p

    for path, p in bfs_all_unique([((), interactive_parser)], expand):
        if predicate(p):
            return path, p

def find_grammar_errors(text: str, start: str='start') -> List[Tuple[UnexpectedInput, str]]:
    errors = []
    def on_error(e):
        errors.append((e, _error_repr(e)))

        # recover to a new line
        token_path, _ = _search_interactive_parser(e.interactive_parser.as_immutable(), lambda p: '_NL' in p.choices())
        for token_type in token_path:
            e.interactive_parser.feed_token(Token(token_type, ''))
        e.interactive_parser.feed_token(Token('_NL', '\n'))
        return True

    _tree = _get_parser().parse(text + '\n', start, on_error=on_error)

    errors_by_line = classify(errors, lambda e: e[0].line)
    errors = [el[0] for el in errors_by_line.values()]      # already sorted

    for e in errors:
        e[0].interactive_parser = None
    return errors
