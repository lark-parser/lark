"Converts between Lark and Nearley grammars. Work in progress!"

import os.path
import sys


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
    return 'n_' + name.replace('$', '__DOLLAR__').lower()

class NearleyToLark(InlineTransformer):
    def __init__(self):
        self._count = 0
        self.extra_rules = {}
        self.extra_rules_rev = {}
        self.alias_js_code = {}

    def _new_function(self, code):
        name = 'alias_%d' % self._count
        self._count += 1

        self.alias_js_code[name] = code
        return name

    def _extra_rule(self, rule):
        if rule in self.extra_rules_rev:
            return self.extra_rules_rev[rule]

        name = 'xrule_%d' % len(self.extra_rules)
        assert name not in self.extra_rules
        self.extra_rules[name] = rule                
        self.extra_rules_rev[rule] = name
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

def _nearley_to_lark(g, builtin_path, n2l, js_code):
    rule_defs = []

    tree = nearley_grammar_parser.parse(g)
    for statement in tree.children:
        if statement.data == 'directive':
            directive, arg = statement.children
            if directive == 'builtin':
                with open(os.path.join(builtin_path, arg[1:-1])) as f:
                    text = f.read()
                rule_defs += _nearley_to_lark(text, builtin_path, n2l, js_code)
            else:
                assert False, directive
        elif statement.data == 'js_code':
            code ,= statement.children
            code = code[2:-2]
            js_code.append(code)
        elif statement.data == 'macro':
            pass    # TODO Add support for macros!
        elif statement.data == 'ruledef':
            rule_defs.append( n2l.transform(statement) )
        else:
            raise Exception("Unknown statement: %s" % statement)

    return rule_defs


def create_code_for_nearley_grammar(g, start, builtin_path):
    import js2py

    emit_code = []
    def emit(x=None):
        if x:
            emit_code.append(x)
        emit_code.append('\n')
    
    js_code = ['function id(x) {return x[0];}']
    n2l = NearleyToLark()
    lark_g = '\n'.join(_nearley_to_lark(g, builtin_path, n2l, js_code))
    lark_g += '\n'+'\n'.join('!%s: %s' % item for item in n2l.extra_rules.items())

    emit('from lark import Lark, Transformer')
    emit()
    emit('grammar = ' + repr(lark_g))
    emit()
    
    for alias, code in n2l.alias_js_code.items():
        js_code.append('%s = (%s);' % (alias, code))

    emit(js2py.translate_js('\n'.join(js_code)))
    emit('class TranformNearley(Transformer):')
    for alias in n2l.alias_js_code:
        emit("    %s = var.get('%s').to_python()" % (alias, alias))
    emit("    __default__ = lambda self, n, c: c if c else None")

    emit()
    emit('parser = Lark(grammar, start="n_%s")' % start)
    emit('def parse(text):')
    emit('    return TranformNearley().transform(parser.parse(text))')

    return ''.join(emit_code)

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
    code = create_code_for_nearley_grammar(css_example_grammar, 'csscolor', '/home/erez/nearley/builtin')
    d = {}
    exec (code, d)
    parse = d['parse']

    print(parse('#a199ff'))
    print(parse('rgb(255, 70%, 3)'))


def main():
    if len(sys.argv) < 3:
        print("Reads Nearley grammar (with js functions) outputs an equivalent lark parser.")
        print("Usage: %s <nearley_grammar_path> <start_rule> <nearley_lib_path>" % sys.argv[0])
        return

    fn, start, nearley_lib = sys.argv[1:]
    with open(fn) as f:
        grammar = f.read()
    print(create_code_for_nearley_grammar(grammar, start, os.path.join(nearley_lib, 'builtin')))


if __name__ == '__main__':
    main()
    # test()
