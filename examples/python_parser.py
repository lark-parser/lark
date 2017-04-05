#
# This example demonstrates usage of the included Python grammars
#

import sys
import os, os.path
from io import open
import glob, time

from lark import Lark
from lark.indenter import Indenter

__path__ = os.path.dirname(__file__)

class PythonIndenter(Indenter):
    NL_type = '_NEWLINE'
    OPEN_PAREN_types = ['__LPAR', '__LSQB', '__LBRACE']
    CLOSE_PAREN_types = ['__RPAR', '__RSQB', '__RBRACE']
    INDENT_type = '_INDENT'
    DEDENT_type = '_DEDENT'
    tab_len = 8


grammar2_filename = os.path.join(__path__, 'python2.g')
grammar3_filename = os.path.join(__path__, 'python3.g')
with open(grammar2_filename) as f:
    python_parser2 = Lark(f, parser='lalr', postlex=PythonIndenter(), start='file_input')
with open(grammar3_filename) as f:
    python_parser3 = Lark(f, parser='lalr', postlex=PythonIndenter(), start='file_input')


with open(grammar2_filename) as f:
    python_parser2_earley = Lark(f, parser='lalr', lexer='standard', postlex=PythonIndenter(), start='file_input')

def _read(fn, *args):
    kwargs = {'encoding': 'iso-8859-1'}
    with open(fn, *args, **kwargs) as f:
        return f.read()

def _get_lib_path():
    if os.name == 'nt':
        if 'PyPy' in sys.version:
            return os.path.join(sys.prefix, 'lib-python', sys.winver)
        else:
            return os.path.join(sys.prefix, 'Lib')
    else:
        return [x for x in sys.path if x.endswith('%s.%s' % sys.version_info[:2])][0]

def test_python_lib():

    path = _get_lib_path()

    start = time.time()
    files = glob.glob(path+'/*.py')
    for f in files:
        print( f )
        try:
            # print list(python_parser.lex(_read(os.path.join(path, f)) + '\n'))
            try:
                xrange
            except NameError:
                python_parser3.parse(_read(os.path.join(path, f)) + '\n')
            else:
                python_parser2.parse(_read(os.path.join(path, f)) + '\n')
        except:
            print ('At %s' % f)
            raise

    end = time.time()
    print( "test_python_lib (%d files), time: %s secs"%(len(files), end-start) )

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
