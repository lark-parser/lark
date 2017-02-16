import json
from .json_parser import json_grammar

from lark import Lark
from lark.reconstruct import Reconstructor

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

    json_parser = Lark(json_grammar)
    tree = json_parser.parse(test_json)

    # print '@@', tree.pretty()
    # for x in tree.find_data('true'):
    #     x.data = 'false'
    #     # x.children[0].value = '"HAHA"'


    new_json = Reconstructor(json_parser).reconstruct(tree)
    print new_json
    print json.loads(new_json) == json.loads(test_json)

test()
