#
# This example demonstrates usage of the included Python grammars
#

import sys
import os, os.path
from io import open
import glob, time

from lark import Lark
from lark.indenter import Indenter

# __path__ = os.path.dirname(__file__)

class PythonIndenter(Indenter):
    NL_type = '_NEWLINE'
    OPEN_PAREN_types = ['LPAR', 'LSQB', 'LBRACE']
    CLOSE_PAREN_types = ['RPAR', 'RSQB', 'RBRACE']
    INDENT_type = '_INDENT'
    DEDENT_type = '_DEDENT'
    tab_len = 8

kwargs = dict(rel_to=__file__, postlex=PythonIndenter(), start='file_input')

python_parser2 = Lark.open('python2.lark', parser='lalr', **kwargs)
python_parser3 = Lark.open('python3.lark',parser='lalr', **kwargs)
python_parser2_earley = Lark.open('python2.lark', parser='earley', lexer='standard', **kwargs)


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
    # python_parser3.parse(_read(sys.argv[1]) + '\n')

