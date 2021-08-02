# Recipes

A collection of recipes to use Lark and its various features


## Use a transformer to parse integer tokens

Transformers are the common interface for processing matched rules and tokens.

They can be used during parsing for better performance.

```python
from lark import Lark, Transformer

class T(Transformer):
    def INT(self, tok):
        "Convert the value of `tok` from string to int, while maintaining line number & column."
        return tok.update(value=int(tok))

parser = Lark("""
start: INT*
%import common.INT
%ignore " "
""", parser="lalr", transformer=T())

print(parser.parse('3 14 159'))
```

Prints out:

```python
Tree(start, [Token(INT, 3), Token(INT, 14), Token(INT, 159)])
```


## Collect all comments with lexer_callbacks

`lexer_callbacks` can be used to interface with the lexer as it generates tokens.

It accepts a dictionary of the form

    {TOKEN_TYPE: callback}

Where callback is of type `f(Token) -> Token`

It only works with the standard and contextual lexers.

This has the same effect of using a transformer, but can also process ignored tokens.

```python
from lark import Lark

comments = []

parser = Lark("""
    start: INT*

    COMMENT: /#.*/

    %import common (INT, WS)
    %ignore COMMENT
    %ignore WS
""", parser="lalr", lexer_callbacks={'COMMENT': comments.append})

parser.parse("""
1 2 3  # hello
# world
4 5 6
""")

print(comments)
```

Prints out:

```python
[Token(COMMENT, '# hello'), Token(COMMENT, '# world')]
```

*Note: We don't have to return a token, because comments are ignored*

## CollapseAmbiguities

Parsing ambiguous texts with earley and `ambiguity='explicit'` produces a single tree with `_ambig` nodes to mark where the ambiguity occurred.

However, it's sometimes more convenient instead to work with a list of all possible unambiguous trees.

Lark provides a utility transformer for that purpose:

```python
from lark import Lark, Tree, Transformer
from lark.visitors import CollapseAmbiguities

grammar = """
    !start: x y

    !x: "a" "b"
      | "ab"
      | "abc"

    !y: "c" "d"
      | "cd"
      | "d"

"""
parser = Lark(grammar, ambiguity='explicit')

t = parser.parse('abcd')
for x in CollapseAmbiguities().transform(t):
    print(x.pretty())
```

This prints out:

    start
    x
        a
        b
    y
        c
        d

    start
    x     ab
    y     cd

    start
    x     abc
    y     d

While convenient, this should be used carefully, as highly ambiguous trees will soon create an exponential explosion of such unambiguous derivations.


## Keeping track of parents when visiting

The following visitor assigns a `parent` attribute for every node in the tree.

If your tree nodes aren't unique (if there is a shared Tree instance), the assert will fail.

```python
class Parent(Visitor):
    def __default__(self, tree):
        for subtree in tree.children:
            if isinstance(subtree, Tree):
                assert not hasattr(subtree, 'parent')
                subtree.parent = tree
```


## Unwinding VisitError after a transformer/visitor exception

Errors that happen inside visitors and transformers get wrapped inside a `VisitError` exception.

This can often be inconvenient, if you wish the actual error to propagate upwards, or if you want to catch it.

But, it's easy to unwrap it at the point of calling the transformer, by catching it and raising the `VisitError.orig_exc` attribute.

For example:
```python
from lark import Lark, Transformer
from lark.visitors import VisitError

tree = Lark('start: "a"').parse('a')

class T(Transformer):
    def start(self, x):
        raise KeyError("Original Exception")

t = T()
try:
    print( t.transform(tree))
except VisitError as e:
    raise e.orig_exc
```