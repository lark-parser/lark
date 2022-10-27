"""
Python 3 to Python 2 converter (tree templates)
===============================================

This example demonstrates how to translate between two trees using tree templates.
It parses Python 3, translates it to a Python 2 AST, and then outputs the result as Python 2 code.

Uses reconstruct_python.py for generating the final Python 2 code.
"""


from lark import Lark
from lark.tree_templates import TemplateConf, TemplateTranslator

from lark.indenter import PythonIndenter
from reconstruct_python import PythonReconstructor


#
# 1. Define a Python parser that also accepts template vars in the code (in the form of $var)
#
TEMPLATED_PYTHON = r"""
%import python (single_input, file_input, eval_input, atom, var, stmt, expr, testlist_star_expr, _NEWLINE, _INDENT, _DEDENT, COMMENT, NAME)

%extend atom: TEMPLATE_NAME -> var

TEMPLATE_NAME: "$" NAME

?template_start: (stmt | testlist_star_expr _NEWLINE)

%ignore /[\t \f]+/          // WS
%ignore /\\[\t \f]*\r?\n/   // LINE_CONT
%ignore COMMENT
"""

parser = Lark(TEMPLATED_PYTHON, parser='lalr', start=['single_input', 'file_input', 'eval_input', 'template_start'], postlex=PythonIndenter(), maybe_placeholders=False)


def parse_template(s):
    return parser.parse(s + '\n', start='template_start')

def parse_code(s):
    return parser.parse(s + '\n', start='file_input')


#
# 2. Define translations using templates (each template code is parsed to a template tree)
#

pytemplate = TemplateConf(parse=parse_template)

translations_3to2 = {
    'yield from $a':
	    'for _tmp in $a: yield _tmp',

    'raise $e from $x':
    	'raise $e',

    '$a / $b':
	    'float($a) / $b',
}
translations_3to2 = {pytemplate(k): pytemplate(v) for k, v in translations_3to2.items()}

#
# 3. Translate and reconstruct Python 3 code into valid Python 2 code
#

python_reconstruct = PythonReconstructor(parser)

def translate_py3to2(code):
	tree = parse_code(code)
	tree = TemplateTranslator(translations_3to2).translate(tree)
	return python_reconstruct.reconstruct(tree)


#
# Test Code
#

_TEST_CODE = '''
if a / 2 > 1:
    yield from [1,2,3]
else:
    raise ValueError(a) from e

'''

def test():
	print(_TEST_CODE)
	print('   ----->    ')
	print(translate_py3to2(_TEST_CODE))

if __name__ == '__main__':
	test()
