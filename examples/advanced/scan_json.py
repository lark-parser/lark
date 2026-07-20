"""
Extracting JSON payloads from arbitrary text with ``Lark.scan``
================================================================

Shows ``Lark.scan`` finding JSON objects and arrays embedded in text.
JSON has a recursive structure, which makes this task very hard for regex,
but straightforward for a parser.

The grammar and ``Transformer`` here are essentially the same as in
``examples/json_parser.py``.
"""

from lark import Lark, Transformer, v_args


example_text = r'''
[2024-05-10 12:00:01] INFO  login: {"user": "alice", "tags": ["admin", "active"]}
[2024-05-10 12:00:05] ERROR auth failed: {
    "user": "bob",
    "attempt": 3,
    "blocked": false,
    "reason": "rate-limited"
}
... that was unexpected; checking next event ...
[2024-05-10 12:00:12] INFO  cart updated: {
    "cart_id": 42,
    "items": [
        {"sku": "X1", "qty": 2, "price": 9.99},
        {"sku": "Y2", "qty": 1, "price": 14.5e1}
    ],
    "promo": null
}
[2024-05-10 12:00:18] INFO  batch: ["a", "b", "c"]
[2024-05-10 12:00:30] DEBUG no payload
'''


json_grammar = r"""
    ?start: object | array

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

    string : ESCAPED_STRING

    %import common.ESCAPED_STRING
    %import common.SIGNED_NUMBER
    %import common.WS

    %ignore WS
"""


class TreeToJson(Transformer):
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


parser = Lark(json_grammar, parser="lalr", transformer=TreeToJson())


print(f"{'Range':<14}  Payload")
print("-" * 90)
for match in parser.scan(example_text):
    print(f"{str(match.range):<14}  {match.value!r}")
