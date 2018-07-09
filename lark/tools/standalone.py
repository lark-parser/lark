###{standalone
#
#
#   Lark Stand-alone Generator Tool
# ----------------------------------
# Generates a stand-alone LALR(1) parser with a standard lexer
#
# Git:    https://github.com/erezsh/lark
# Author: Erez Shinan (erezshin@gmail.com)
#
#
#    >>> LICENSE
#
#    This tool and its generated code use a separate license from Lark.
#
#    It is licensed under GPLv2 or above.
#
#    If you wish to purchase a commercial license for this tool and its
#    generated code, contact me via email.
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 2 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    See <http://www.gnu.org/licenses/>.
#
#
###}

import codecs
import sys
import os
from pprint import pprint
from os import path
from collections import defaultdict

import lark
from lark import Lark
from lark.parsers.lalr_analysis import Shift, Reduce

from ..grammar import Rule

_dir = path.dirname(__file__)
_larkdir = path.join(_dir, path.pardir)


EXTRACT_STANDALONE_FILES = [
    'tools/standalone.py',
    'utils.py',
    'common.py',
    'tree.py',
    'indenter.py',
    'lexer.py',
    'parse_tree_builder.py',
    'parsers/lalr_parser.py',
]


def extract_sections(lines):
    section = None
    text = []
    sections = defaultdict(list)
    for l in lines:
        if l.startswith('###'):
            if l[3] == '{':
                section = l[4:].strip()
            elif l[3] == '}':
                sections[section] += text
                section = None
                text = []
            else:
                raise ValueError(l)
        elif section:
            text.append(l)

    return {name:''.join(text) for name, text in sections.items()}

class LexerAtoms:
    def __init__(self, lexer):
        self.mres = [(p.pattern,d) for p,d in lexer.mres]
        self.newline_types = lexer.newline_types
        self.ignore_types = lexer.ignore_types
        self.callback = {name:[(p.pattern,d) for p,d in c.mres]
                         for name, c in lexer.callback.items()}

    def print_python(self):
        print('import re')
        print('MRES = (')
        pprint(self.mres)
        print(')')
        print('LEXER_CALLBACK = (')
        pprint(self.callback)
        print(')')
        print('NEWLINE_TYPES = %s' % self.newline_types)
        print('IGNORE_TYPES = %s' % self.ignore_types)
        print('class LexerRegexps: pass')
        print('lexer_regexps = LexerRegexps()')
        print('lexer_regexps.mres = [(re.compile(p), d) for p, d in MRES]')
        print('lexer_regexps.callback = {n: UnlessCallback([(re.compile(p), d) for p, d in mres])')
        print('                          for n, mres in LEXER_CALLBACK.items()}')
        print('lexer = _Lex(lexer_regexps)')
        print('def lex(stream):')
        print('    return lexer.lex(stream, NEWLINE_TYPES, IGNORE_TYPES)')


class GetRule:
    def __init__(self, rule_id):
        self.rule_id = rule_id

    def __repr__(self):
        return 'RULES[%d]' % self.rule_id

rule_ids = {}
token_types = {}

def _get_token_type(token_type):
    if token_type not in token_types:
        token_types[token_type] = len(token_types)
    return token_types[token_type]

class ParserAtoms:
    def __init__(self, parser):
        self.parse_table = parser._parse_table

    def print_python(self):
        print('class ParseTable: pass')
        print('parse_table = ParseTable()')
        print('STATES = {')
        for state, actions in self.parse_table.states.items():
            print('  %r: %r,' % (state, {_get_token_type(token): ((1, rule_ids[arg]) if action is Reduce else (0, arg))
                            for token, (action, arg) in actions.items()}))
        print('}')
        print('TOKEN_TYPES = (')
        pprint({v:k for k, v in token_types.items()})
        print(')')
        print('parse_table.states = {s: {TOKEN_TYPES[t]: (a, RULES[x] if a is Reduce else x) for t, (a, x) in acts.items()}')
        print('                      for s, acts in STATES.items()}')
        print('parse_table.start_state = %s' % self.parse_table.start_state)
        print('parse_table.end_state = %s' % self.parse_table.end_state)
        print('class Lark_StandAlone:')
        print('  def __init__(self, transformer=None, postlex=None):')
        print('     callback = parse_tree_builder.create_callback(transformer=transformer)')
        print('     callbacks = {rule: getattr(callback, rule.alias or rule.origin, None) for rule in RULES.values()}')
        print('     self.parser = _Parser(parse_table, callbacks)')
        print('     self.postlex = postlex')
        print('  def parse(self, stream):')
        print('     tokens = lex(stream)')
        print('     if self.postlex: tokens = self.postlex.process(tokens)')
        print('     return self.parser.parse(tokens)')

class TreeBuilderAtoms:
    def __init__(self, lark):
        self.rules = lark.rules
        self.ptb = lark._parse_tree_builder

    def print_python(self):
        print('RULES = {')
        for i, r in enumerate(self.rules):
            rule_ids[r] = i
            print('  %d: Rule(%r, %r, %r, %r),' % (i, r.origin, r.expansion, self.ptb.user_aliases[r], r.options ))
        print('}')
        print('parse_tree_builder = ParseTreeBuilder(RULES.values(), Tree)')

def main(fobj, start):
    lark_inst = Lark(fobj, parser="lalr", lexer="standard", start=start)

    lexer_atoms = LexerAtoms(lark_inst.parser.lexer)
    parser_atoms = ParserAtoms(lark_inst.parser.parser)
    tree_builder_atoms = TreeBuilderAtoms(lark_inst)

    print('# The file was automatically generated by Lark v%s' % lark.__version__)

    for pyfile in EXTRACT_STANDALONE_FILES:
        with open(os.path.join(_larkdir, pyfile)) as f:
            print (extract_sections(f)['standalone'])

    with open(os.path.join(_larkdir, 'grammar.py')) as grammar_py:
        print(grammar_py.read())

    print('Shift = 0')
    print('Reduce = 1')
    lexer_atoms.print_python()
    tree_builder_atoms.print_python()
    parser_atoms.print_python()

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Lark Stand-alone Generator Tool")
        print("Usage: python -m lark.tools.standalone <grammar-file> [<start>]")
        sys.exit(1)

    if len(sys.argv) == 3:
        fn, start = sys.argv[1:]
    elif len(sys.argv) == 2:
        fn, start = sys.argv[1], 'start'
    else:
        assert False, sys.argv

    with codecs.open(fn, encoding='utf8') as f:
        main(f, start)
