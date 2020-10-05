import sys
from argparse import ArgumentParser, FileType
from lark import Lark

base_argparser = ArgumentParser(add_help=False, epilog='Look at the Lark documentation for more info on the options')


flags = [
    ('d', 'debug'),
    'keep_all_tokens',
    'regex',
    'propagate_positions',
    'maybe_placeholders',
    'use_bytes'
]

options = ['start', 'lexer']

base_argparser.add_argument('-s', '--start', action='append', default=[])
base_argparser.add_argument('-l', '--lexer', default='contextual', choices=('standard', 'contextual'))
k = {'encoding':'utf-8'} if sys.version_info > (3, 4) else {}
base_argparser.add_argument('-o', '--out', type=FileType('w', **k), default=sys.stdout, help='the output file (default=stdout)')
base_argparser.add_argument('grammar_file', type=FileType('r', **k), help='A valid .lark file')

for f in flags:
    if isinstance(f, tuple):
        options.append(f[1])
        base_argparser.add_argument('-' + f[0], '--' + f[1], action='store_true')
    else:
        options.append(f)
        base_argparser.add_argument('--' + f, action='store_true')

def build_lalr(namespace):
    if len(namespace.start) == 0:
        namespace.start.append('start')
    kwargs = {n: getattr(namespace, n) for n in options}
    return Lark(namespace.grammar_file, parser='lalr', **kwargs), namespace.out