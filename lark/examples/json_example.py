import sys
from lark.lark import Lark
from lark.tree import Transformer

json_grammar = r"""
    ?start: value

    ?value: object
          | array
          | string
          | number
          | "true"             -> *true
          | "false"            -> *false
          | "null"             -> *null

    array  : "[" [value ("," value)*] "]"
    object : "{" [pair ("," pair)*] "}"
    pair   : string ":" value

    *number : /-?\d+(\.\d+)?([eE][+-]?\d+)?/
    *string : /".*?(?<!\\)"/

    WS.ignore.newline: /[ \t\n]+/
"""

class TreeToJson(Transformer):
    def string(self, s):
        return s[1:-1]

    array = list
    pair = tuple
    object = dict
    number = float

    null = lambda self: None
    true = lambda self: True
    false = lambda self: False

json_parser = Lark(json_grammar, parser='lalr', transformer=TreeToJson())

def test():
    test_json = '''
        {
            "empty_object" : {},
            "empty_array"  : [],
            "booleans"     : { "YES" : true, "NO" : false },
            "numbers"      : [ 0, 1, -2, 3.3, 4.4e5, 6.6e-7 ],
            "strings"      : [ "This", [ "And" , "That" ] ],
            "nothing"      : null
        }
    '''

    j = json_parser.parse(test_json)
    print j
    import json
    assert j == json.loads(test_json)

if __name__ == '__main__':
    test()
    with open(sys.argv[1]) as f:
        print json_parser.parse(f.read())

