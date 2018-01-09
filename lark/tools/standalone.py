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

from ..grammar import Rule

__dir__ = path.dirname(__file__)
__larkdir__ = path.join(__dir__, path.pardir)


EXTRACT_STANDALONE_FILES = [
    'tools/standalone.py',
    'utils.py',
    'common.py',
    'tree.py',
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
        assert not lexer.callback
        self.mres = [(p.pattern,d) for p,d in lexer.mres]
        self.newline_types = lexer.newline_types
        self.ignore_types = lexer.ignore_types

    def print_python(self):
        print('import re')
        print('MRES = (')
        pprint(self.mres)
        print(')')
        print('NEWLINE_TYPES = %s' % self.newline_types)
        print('IGNORE_TYPES = %s' % self.ignore_types)
        print('class LexerRegexps: pass')
        print('lexer_regexps = LexerRegexps()')
        print('lexer_regexps.mres = [(re.compile(p), d) for p, d in MRES]')
        print('lexer_regexps.callback = {}')
        print('lexer = _Lex(lexer_regexps)')
        print('def lex(stream):')
        print('    return lexer.lex(stream, NEWLINE_TYPES, IGNORE_TYPES)')


class GetRule:
    def __init__(self, rule_id):
        self.rule_id = rule_id

    def __repr__(self):
        return 'RULE_ID[%d]' % self.rule_id


def get_rule_ids(x):
    if isinstance(x, (tuple, list)):
        return type(x)(map(get_rule_ids, x))
    elif isinstance(x, dict):
        return {get_rule_ids(k):get_rule_ids(v) for k, v in x.items()}
    elif isinstance(x, Rule):
        return GetRule(id(x))
    return x

class ParserAtoms:
    def __init__(self, parser):
        self.parse_table = parser.analysis.parse_table

    def print_python(self):
        print('class ParseTable: pass')
        print('parse_table = ParseTable()')
        print('parse_table.states = (')
        pprint(get_rule_ids(self.parse_table.states))
        print(')')
        print('parse_table.start_state = %s' % self.parse_table.start_state)
        print('parse_table.end_state = %s' % self.parse_table.end_state)
        print('class Lark_StandAlone:')
        print('  def __init__(self, transformer=None):')
        print('     callback = parse_tree_builder.create_callback(transformer=transformer)')
        print('     callbacks = {rule: getattr(callback, rule.alias or rule.origin, None) for rule in RULES}')
        print('     self.parser = _Parser(parse_table, callbacks)')
        print('  def parse(self, stream):')
        print('     return self.parser.parse(lex(stream))')

class TreeBuilderAtoms:
    def __init__(self, lark):
        self.rules = lark.rules
        self.ptb = lark._parse_tree_builder

    def print_python(self):
        print('RULE_ID = {')
        for r in self.rules:
            print(' %d: Rule(%r, %r, %r, %r),' % (id(r), r.origin, r.expansion, self.ptb.user_aliases[r], r.options ))
        print('}')
        print('RULES = list(RULE_ID.values())')
        print('parse_tree_builder = ParseTreeBuilder(RULES, Tree)')

def main(fn):
    with codecs.open(fn, encoding='utf8') as f:
        lark_inst = Lark(f, parser="lalr")

    lexer_atoms = LexerAtoms(lark_inst.parser.lexer)
    parser_atoms = ParserAtoms(lark_inst.parser.parser)
    tree_builder_atoms = TreeBuilderAtoms(lark_inst)

    print('# The file was automatically generated by Lark v%s' % lark.__version__)

    for pyfile in EXTRACT_STANDALONE_FILES:
        print (extract_sections(open(os.path.join(__larkdir__, pyfile)))['standalone'])

    print(open(os.path.join(__larkdir__, 'grammar.py')).read())
    print('Shift = 0')
    print('Reduce = 1')
    lexer_atoms.print_python()
    tree_builder_atoms.print_python()
    parser_atoms.print_python()

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Lark Stand-alone Generator Tool")
        print("Usage: python -m lark.tools.standalone <grammar-file>")
        sys.exit(1)

    fn ,= sys.argv[1:]

    main(fn)
