"Converts between Lark and Nearley grammars. Work in progress!"

import os.path
import sys

import js2py

from lark import Lark, InlineTransformer, Transformer

nearley_grammar = r"""
    start: (ruledef|directive)+

    directive: "@" NAME (STRING|NAME)
             | "@" JS  -> js_code
    ruledef: NAME "->" expansions
           | NAME REGEXP "->" expansions -> macro
    expansions: expansion ("|" expansion)*

    expansion: expr+ js

    ?expr: item [":" /[+*?]/]

    ?item: rule|string|regexp
         | "(" expansions ")"

    rule: NAME
    string: STRING
    regexp: REGEXP
    JS: /(?s){%.*?%}/
    js: JS?

    NAME: /[a-zA-Z_$]\w*/
    COMMENT: /\#[^\n]*/
    REGEXP: /\[.*?\]/
    STRING: /".*?"/

    %import common.WS
    %ignore WS
    %ignore COMMENT

    """

nearley_grammar_parser = Lark(nearley_grammar, parser='earley', lexer='standard')

def _get_rulename(name):
    name = {'_': '_ws_maybe', '__':'_ws'}.get(name, name)
    return 'n_' + name.replace('$', '__DOLLAR__')

class NearleyToLark(InlineTransformer):
    def __init__(self, context):
        self.context = context
        self.functions = {}
        self.extra_rules = {}

    def _new_function(self, code):
        n = len(self.functions)
        name = 'alias_%d' % n
        assert name not in self.functions
        code = "%s = (%s);" % (name, code)
        self.context.execute(code)
        f = getattr(self.context, name)
        self.functions[name] = f

        return name

    def _extra_rule(self, rule):
        name = 'xrule_%d' % len(self.extra_rules)
        assert name not in self.extra_rules
        self.extra_rules[name] = rule                
        return name

    def rule(self, name):
        return _get_rulename(name)

    def ruledef(self, name, exps):
        return '!%s: %s' % (_get_rulename(name), exps)

    def expr(self, item, op):
        rule = '(%s)%s' % (item, op)
        return self._extra_rule(rule)

    def regexp(self, r):
        return '/%s/' % r

    def string(self, s):
        return self._extra_rule(s)

    def expansion(self, *x):
        x, js = x[:-1], x[-1]
        if js.children:
            js_code ,= js.children
            js_code = js_code[2:-2]
            alias = '-> ' + self._new_function(js_code)
        else:
            alias = ''
        return ' '.join(x) + alias

    def expansions(self, *x):
        return '%s' % ('\n    |'.join(x))

    def start(self, *rules):
        return '\n'.join(filter(None, rules))

def _nearley_to_lark(g, builtin_path, n2l):
    rule_defs = []

    tree = nearley_grammar_parser.parse(g)
    for statement in tree.children:
        if statement.data == 'directive':
            directive, arg = statement.children
            if directive == 'builtin':
                with open(os.path.join(builtin_path, arg[1:-1])) as f:
                    text = f.read()
                rule_defs += _nearley_to_lark(text, builtin_path, n2l)
            else:
                assert False, directive
        elif statement.data == 'js_code':
            code ,= statement.children
            code = code[2:-2]
            n2l.context.execute(code)
        elif statement.data == 'macro':
            pass    # TODO Add support for macros!
        elif statement.data == 'ruledef':
            rule_defs.append( n2l.transform(statement) )
        else:
            raise Exception("Unknown statement: %s" % statement)

    return rule_defs


def nearley_to_lark(g, builtin_path, context):
    n2l = NearleyToLark(context)
    lark_g = '\n'.join(_nearley_to_lark(g, builtin_path, n2l))
    lark_g += '\n'+'\n'.join('!%s: %s' % item for item in n2l.extra_rules.items())
    t = Transformer()
    for fname, fcode in n2l.functions.items():
        setattr(t, fname, fcode)
    setattr(t, '__default__', lambda n, c: c if c else None)

    return lark_g, t


def test():
    css_example_grammar = """
# http://www.w3.org/TR/css3-color/#colorunits

    @builtin "whitespace.ne"
    @builtin "number.ne"
    @builtin "postprocessors.ne"

    csscolor -> "#" hexdigit hexdigit hexdigit hexdigit hexdigit hexdigit {%
        function(d) {
            return {
                "r": parseInt(d[1]+d[2], 16),
                "g": parseInt(d[3]+d[4], 16),
                "b": parseInt(d[5]+d[6], 16),
            }
        }
    %}
              | "#" hexdigit hexdigit hexdigit {%
        function(d) {
            return {
                "r": parseInt(d[1]+d[1], 16),
                "g": parseInt(d[2]+d[2], 16),
                "b": parseInt(d[3]+d[3], 16),
            }
        }
    %}
              | "rgb"  _ "(" _ colnum _ "," _ colnum _ "," _ colnum _ ")" {% $({"r": 4, "g": 8, "b": 12}) %}
              | "hsl"  _ "(" _ colnum _ "," _ colnum _ "," _ colnum _ ")" {% $({"h": 4, "s": 8, "l": 12}) %}
              | "rgba" _ "(" _ colnum _ "," _ colnum _ "," _ colnum _ "," _ decimal _ ")" {% $({"r": 4, "g": 8, "b": 12, "a": 16}) %}
              | "hsla" _ "(" _ colnum _ "," _ colnum _ "," _ colnum _ "," _ decimal _ ")" {% $({"h": 4, "s": 8, "l": 12, "a": 16}) %}

    hexdigit -> [a-fA-F0-9]
    colnum -> unsigned_int {% id %} | percentage {%
        function(d) {return Math.floor(d[0]*255); }
    %}
    """
    context = js2py.EvalJs()
    context.execute('function id(x) {return x[0]; }')

    converted_grammar, t = nearley_to_lark(css_example_grammar, '/home/erez/nearley/builtin', context)
    # print(converted_grammar)

    l = Lark(converted_grammar, start='n_csscolor')
    tree = l.parse('#a199ff')
    print(t.transform(tree))
    tree = l.parse('rgb(255, 70%, 3)')
    print(t.transform(tree))


def main():
    try:
        nearley_lib = sys.argv[1]
    except IndexError:
        print("Reads Nearley grammar from stdin and outputs a lark grammar.")
        print("Usage: %s <nearley_lib_path>" % sys.argv[0])
        return

    grammar = sys.stdin.read()
    print(nearley_to_lark(grammar, os.path.join(nearley_lib, 'builtin')))


if __name__ == '__main__':
    main()
    # test()
