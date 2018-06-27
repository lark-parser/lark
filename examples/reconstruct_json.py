#
# This example demonstrates an experimental feature: Text reconstruction
# The Reconstructor takes a parse tree (already filtered from punctuation, of course),
# and reconstructs it into correct text, that can be parsed correctly.
# It can be useful for creating "hooks" to alter data before handing it to other parsers. You can also use it to generate samples from scratch.
#

import json

from lark import Lark
from lark.reconstruct import Reconstructor

from .json_parser import json_grammar

test_json = '''
    {
        "empty_object" : {},
        "empty_array"  : [],
        "booleans"     : { "YES" : true, "NO" : false },
        "numbers"      : [ 0, 1, -2, 3.3, 4.4e5, 6.6e-7 ],
        "strings"      : [ "This", [ "And" , "That", "And a \\"b" ] ],
        "nothing"      : null
    }
'''

def test_earley():

    json_parser = Lark(json_grammar)
    tree = json_parser.parse(test_json)

    # print ('@@', tree.pretty())
    # for x in tree.find_data('true'):
    #     x.data = 'false'
    #     # x.children[0].value = '"HAHA"'


    new_json = Reconstructor(json_parser).reconstruct(tree)
    print (new_json)
    print (json.loads(new_json) == json.loads(test_json))


def test_lalr():

    json_parser = Lark(json_grammar, parser='lalr')
    tree = json_parser.parse(test_json)

    new_json = Reconstructor(json_parser).reconstruct(tree)
    print (new_json)
    print (json.loads(new_json) == json.loads(test_json))

test_earley()
test_lalr()
