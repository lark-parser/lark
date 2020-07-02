from lark import Lark, Transformer, Discard, v_args

grammar = r"""
start: statement+

?statement: rule
         | terminal
         | "parser"? "grammar" name ";" -> ignore
         | "options" _CODE -> ignore

rule: RULE ":" expansions ";"
terminal: "fragment"? TOKEN ":" term_expansions ";"

?expansions: alias ("|" alias)*

?alias: expansion ["#" name]

?term_expansions: term_alias ("|" term_alias)*
?term_alias: term_expansion ["->" name ["(" name ")"]]
term_expansion: expr*

?expansion: expr*

?expr: atom OP?

?atom: "(" expansions ")"
     | value
     | _CODE -> ignore
     | "~" atom -> not_

?value: name
      | STRING -> string
      | REGEXP -> regexp

name: RULE
    | TOKEN

OP: /[+*][?]?|[?](?![a-z])/
RULE: /[a-z][_a-zA-Z0-9]*/
TOKEN: /[A-Z][_a-zA-Z0-9]*/
REGEXP: /\[.*?\]|\./

_STRING_INNER: /.*?/
_STRING_ESC_INNER: _STRING_INNER /(?<!\\)(\\\\)*?/
STRING : "'" _STRING_ESC_INNER "'"

%import common.INT -> NUMBER
%import common.WS

COMMENT: /\s*/ "//" /[^\n]/*
COMMENT2: /\/\*.*?\*\//s
_CODE: /{.*?}/s

%ignore WS
%ignore COMMENT
%ignore COMMENT2

"""

parser = Lark(grammar, parser='lalr')

class T(Transformer):
    def ignore(self, args):
        raise Discard()

    def expansions(self, x):
        return '\n    | '.join(x)

    def term_expansions(self, x):
        return '\n    | '.join(x)

    def term_alias(self, x):
        # TODO channel hidden -> ignore
        return x[0]

    def expansion(self, x):
        return "(" + ' '.join(x) + ")"

    def term_expansion(self, x):
        return "(" + ' '.join(x) + ")"

    @v_args(inline=True)
    def expr(self, expr, op):
        return expr + op.value

    @v_args(inline=True)
    def rule(self, name, exprs):
        return name + ": " + exprs

    @v_args(inline=True)
    def terminal(self, name, exprs):
        if not isinstance(exprs, str):
            breakpoint()
        return name + ": " + exprs

    @v_args(inline=True)
    def name(self, t):
        return t.value

    @v_args(inline=True)
    def string(self, t):
        return t.value.replace('\\', '\\\\').replace('"', '\\"').replace("'", '"')

    @v_args(inline=True)
    def regexp(self, t):
        return f'/{t.value}/'

    @v_args(inline=True)
    def not_(self, t):
        return f" /(?!){t}/ "

    def start(self, stmts):
        return '\n\n'.join(stmts)


with open('SQLite.g4') as f:
    res = parser.parse(f.read())
    # print('###', res.pretty())
    res = T().transform(res)

with open('sqlite.lark', 'w') as f:
    f.write(res)