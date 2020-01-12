#
# This is a toy example that compiles Python directly to bytecode, without generating an AST.
# It currently only works for very very simple Python code.
#
# It requires the 'bytecode' library. You can get it using
#
#     $ pip install bytecode
#

from lark import Lark, Transformer, v_args
from lark.indenter import Indenter

from bytecode import Instr, Bytecode

class PythonIndenter(Indenter):
    NL_type = '_NEWLINE'
    OPEN_PAREN_types = ['LPAR', 'LSQB', 'LBRACE']
    CLOSE_PAREN_types = ['RPAR', 'RSQB', 'RBRACE']
    INDENT_type = '_INDENT'
    DEDENT_type = '_DEDENT'
    tab_len = 8


@v_args(inline=True)
class Compile(Transformer):
    def number(self, n):
        return [Instr('LOAD_CONST', int(n))]
    def string(self, s):
        return [Instr('LOAD_CONST', s[1:-1])]
    def var(self, n):
        return [Instr('LOAD_NAME', n)]

    def arith_expr(self, a, op, b):
        # TODO support chain arithmetic
        assert op == '+'
        return a + b + [Instr('BINARY_ADD')]

    def arguments(self, args):
        return args

    def funccall(self, name, args):
        return name + args + [Instr('CALL_FUNCTION', 1)]

    @v_args(inline=False)
    def file_input(self, stmts):
        return sum(stmts, []) + [Instr("RETURN_VALUE")]

    def expr_stmt(self, lval, rval):
        # TODO more complicated than that
        name ,= lval
        assert name.name == 'LOAD_NAME' # XXX avoid with another layer of abstraction
        return rval + [Instr("STORE_NAME", name.arg)]

    def __default__(self, *args):
        assert False, args


python_parser3 = Lark.open('python3.lark', rel_to=__file__, start='file_input',
                           parser='lalr', postlex=PythonIndenter(),
                           transformer=Compile(), propagate_positions=False)

def compile_python(s):
    insts = python_parser3.parse(s+"\n")
    return Bytecode(insts).to_code()

code = compile_python("""
a = 3
b = 5
print("Hello World!")
print(a+(b+2))
print((a+b)+2)
""")
exec(code)
# -- Output --
# Hello World!
# 10
# 10
