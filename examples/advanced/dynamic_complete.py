"""
Using lexer dynamic_complete
============================

Demonstrates how to use ``lexer='dynamic_complete'`` and ``ambiguity='explicit'``

Sometimes you have data that is highly ambiguous or 'broken' in some sense.
When using ``parser='earley'`` and ``lexer='dynamic_complete'``, Lark will be able
parse just about anything as long as there is a valid way to generate it from
the Grammar, including looking 'into' the Regexes.

This examples shows how to parse a json input where the quotes have been
replaced by underscores: ``{_foo_:{}, _bar_: [], _baz_: __}``
Notice that underscores might still appear inside strings, so a potentially
valid reading of the above is:
``{"foo_:{}, _bar": [], "baz": ""}``
"""
from pprint import pprint

from lark import Lark, Tree, Transformer, v_args
from lark.visitors import Transformer_InPlace

GRAMMAR = r"""
%import common.SIGNED_NUMBER
%import common.WS_INLINE
%import common.NEWLINE
%ignore WS_INLINE

?start: value

?value: object
      | array
      | string
      | SIGNED_NUMBER      -> number
      | "true"             -> true
      | "false"            -> false
      | "null"             -> null

array  : "[" (value ("," value)*)? "]"
object : "{" (pair ("," pair)*)? "}"
pair   : string ":" value

string: STRING
STRING : ESCAPED_STRING

ESCAPED_STRING: QUOTE_CHAR _STRING_ESC_INNER QUOTE_CHAR
QUOTE_CHAR: "_"

_STRING_INNER: /.*/
_STRING_ESC_INNER: _STRING_INNER /(?<!\\)(\\\\)*?/

"""


def score(tree: Tree):
    """
    Scores an option by how many children (and grand-children, and
    grand-grand-children, ...) it has.
    This means that the option with fewer large terminals gets selected

    Between
        object
          pair
            string	_foo_
            object
          pair
            string	_bar_: [], _baz_
            string	__

    and

        object
          pair
            string	_foo_
            object
          pair
            string	_bar_
            array
          pair
            string	_baz_
            string	__

    this will give the second a higher score. (9 vs 13)
    """
    return sum(len(t.children) for t in tree.iter_subtrees())


class RemoveAmbiguities(Transformer_InPlace):
    """
    Selects an option to resolve an ambiguity using the score function above.
    Scores each option and selects the one with the higher score, e.g. the one
    with more nodes.

    If there is a performance problem with the Tree having to many _ambig and
    being slow and to large, this can instead be written as a ForestVisitor.
    Look at the 'Custom SPPF Prioritizer' example.
    """
    def _ambig(self, options):
        return max(options, key=score)


class TreeToJson(Transformer):
    """
    This is the same Transformer as the json_parser example.
    """
    @v_args(inline=True)
    def string(self, s):
        return s[1:-1].replace('\\"', '"')

    array = list
    pair = tuple
    object = dict
    number = v_args(inline=True)(float)

    null = lambda self, _: None
    true = lambda self, _: True
    false = lambda self, _: False


parser = Lark(GRAMMAR, parser='earley', ambiguity="explicit", lexer='dynamic_complete')

EXAMPLES = [
    r'{_array_:[1,2,3]}',

    r'{_abc_: _array must be of the following format [_1_, _2_, _3_]_}',

    r'{_foo_:{}, _bar_: [], _baz_: __}',

    r'{_error_:_invalid_client_, _error_description_:_AADSTS7000215: Invalid '
    r'client secret is provided.\r\nTrace ID: '
    r'a0a0aaaa-a0a0-0a00-000a-00a00aaa0a00\r\nCorrelation ID: '
    r'aa0aaa00-0aaa-0000-00a0-00000aaaa0aa\r\nTimestamp: 1997-10-10 00:00:00Z_, '
    r'_error_codes_:[7000215], _timestamp_:_1997-10-10 00:00:00Z_, '
    r'_trace_id_:_a0a0aaaa-a0a0-0a00-000a-00a00aaa0a00_, '
    r'_correlation_id_:_aa0aaa00-0aaa-0000-00a0-00000aaaa0aa_, '
    r'_error_uri_:_https://example.com_}',

]
for example in EXAMPLES:
    tree = parser.parse(example)
    tree = RemoveAmbiguities().transform(tree)
    result = TreeToJson().transform(tree)
    pprint(result)
