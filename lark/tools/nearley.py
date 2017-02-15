"Converts between Lark and Nearley grammars. Work in progress!"

import os.path
import sys

from lark import Lark, InlineTransformer

nearley_grammar = r"""
    start: (ruledef|directive)+

    directive: "@" NAME (STRING|NAME)
             | "@" _JS  -> js_code
    ruledef: NAME "->" expansions
           | NAME REGEXP "->" expansions -> macro
    expansions: expansion ("|" expansion)*

    expansion: expr+ _JS?

    ?expr: item [":" /[+*?]/]

    ?item: rule|string|regexp
         | "(" expansions ")"

    rule: NAME
    string: STRING
    regexp: REGEXP
    _JS: /(?s){%.*?%}/

    NAME: /[a-zA-Z_$]\w*/
    WS.ignore: /[\t \f\n]+/
    COMMENT.ignore: /\#[^\n]*/
    REGEXP: /\[.*?\]/
    STRING: /".*?"/

    """



class NearleyToLark(InlineTransformer):
    def __init__(self, builtin_path):
        self.builtin_path = builtin_path

    def rule(self, name):
        # return {'_': '_WS?', '__':'_WS'}.get(name, name)
        return {'_': '_ws_maybe', '__':'_ws'}.get(name, name)

    def ruledef(self, name, exps):
        name = {'_': '_ws_maybe', '__':'_ws'}.get(name, name)
        return '%s: %s' % (name, exps)

    def expr(self, item, op):
        return '(%s)%s' % (item, op)

    def regexp(self, r):
        return '/%s/' % r

    def string(self, s):
        # TODO allow regular strings, and split them in the parser frontend
        return ' '.join('"%s"'%ch for ch in s[1:-1])

    def expansion(self, *x):
        return ' '.join(x)

    def expansions(self, *x):
        return '(%s)' % ('\n    |'.join(x))

    def js_code(self):
        return ''

    def macro(self, *args):
        return ''   # TODO support macros?!

    def directive(self, name, *args):
        if name == 'builtin':
            arg = args[0][1:-1]
            with open(os.path.join(self.builtin_path, arg)) as f:
                text = f.read()
            return nearley_to_lark(text, self.builtin_path)
        elif name == 'preprocessor':
            return ''

        raise Exception('Unknown directive: %s' % name)

    def start(self, *rules):
        return '\n'.join(filter(None, rules))

def nearley_to_lark(g, builtin_path):
    parser = Lark(nearley_grammar)
    tree = parser.parse(g)
    return NearleyToLark(builtin_path).transform(tree)


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
    converted_grammar = nearley_to_lark(css_example_grammar, '/home/erez/nearley/builtin')
    print(converted_grammar)

    l = Lark(converted_grammar, start='csscolor', parser='earley_nolex')
    print(l.parse('#a199ff').pretty())
    print(l.parse('rgb(255, 70%, 3)').pretty())


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
