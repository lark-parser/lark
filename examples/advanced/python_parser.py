"""
Grammar-complete Python Parser
==============================

A fully-working Python 2 & 3 parser (but not production ready yet!)

This example demonstrates usage of the included Python grammars
"""
import sys
import os, os.path
from io import open
import glob, time

from lark import Lark
from lark.indenter import PythonIndenter


kwargs = dict(postlex=PythonIndenter(), start='file_input')

# Official Python grammar by Lark
python_parser3 = Lark.open_from_package('lark', 'python.lark', ['grammars'], parser='lalr', **kwargs)

# Local Python2 grammar
python_parser2 = Lark.open('python2.lark', rel_to=__file__, parser='lalr', **kwargs)
python_parser2_earley = Lark.open('python2.lark', rel_to=__file__, parser='earley', lexer='basic', **kwargs)

try:
    xrange
except NameError:
    chosen_parser = python_parser3
else:
    chosen_parser = python_parser2


def _read(fn, *args):
    kwargs = {'encoding': 'iso-8859-1'}
    with open(fn, *args, **kwargs) as f:
        return f.read()

def _get_lib_path():
    if os.name == 'nt':
        if 'PyPy' in sys.version:
            return os.path.join(sys.base_prefix, 'lib-python', sys.winver)
        else:
            return os.path.join(sys.base_prefix, 'Lib')
    else:
        return [x for x in sys.path if x.endswith('%s.%s' % sys.version_info[:2])][0]

def test_python_lib():
    path = _get_lib_path()

    start = time.time()
    files = glob.glob(path+'/*.py')
    total_kb = 0
    for f in files:
        r = _read(os.path.join(path, f))
        kb = len(r) / 1024
        print( '%s -\t%.1f kb' % (f, kb))
        chosen_parser.parse(r + '\n')
        total_kb += kb

    end = time.time()
    print( "test_python_lib (%d files, %.1f kb), time: %.2f secs"%(len(files), total_kb, end-start) )

def test_earley_equals_lalr():
    path = _get_lib_path()

    files = glob.glob(path+'/*.py')
    for f in files:
        print( f )
        tree1 = python_parser2.parse(_read(os.path.join(path, f)) + '\n')
        tree2 = python_parser2_earley.parse(_read(os.path.join(path, f)) + '\n')
        assert tree1 == tree2


if __name__ == '__main__':
    test_python_lib()
    # test_earley_equals_lalr()
    # python_parser3.parse(_read(sys.argv[1]) + '\n')
