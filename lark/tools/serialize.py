import codecs
import sys
import json

from lark import Lark
from lark.grammar import RuleOptions, Rule
from lark.lexer import TerminalDef

import argparse

argparser = argparse.ArgumentParser(prog='python -m lark.tools.serialize') #description='''Lark Serialization Tool -- Stores Lark's internal state & LALR analysis as a convenient JSON file''')

argparser.add_argument('grammar_file', type=argparse.FileType('r'), help='A valid .lark file')
argparser.add_argument('-o', '--out', type=argparse.FileType('w'), default=sys.stdout, help='json file path to create (default=stdout)')
argparser.add_argument('-s', '--start', default='start', help='start symbol (default="start")', nargs='+')
argparser.add_argument('-l', '--lexer', default='standard', choices=['standard', 'contextual'], help='lexer type (default="standard")')


def serialize(infile, outfile, lexer, start):
    lark_inst = Lark(infile, parser="lalr", lexer=lexer, start=start)    # TODO contextual

    data, memo = lark_inst.memo_serialize([TerminalDef, Rule])
    outfile.write('{\n')
    outfile.write('  "data": %s,\n' % json.dumps(data))
    outfile.write('  "memo": %s\n' % json.dumps(memo))
    outfile.write('}\n')


def main():
    if len(sys.argv) == 1 or '-h' in sys.argv or '--help' in sys.argv:
        print("Lark Serialization Tool - Stores Lark's internal state & LALR analysis as a JSON file")
        print("")
        argparser.print_help()
    else:
        args = argparser.parse_args()
        serialize(args.grammar_file, args.out, args.lexer, args.start)

if __name__ == '__main__':
    main()