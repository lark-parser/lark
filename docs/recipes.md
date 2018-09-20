# Recipes

A collection of recipes to use Lark and its various features



## lexer_callbacks

Use it to interface with the lexer as it generates tokens.

Accepts a dictionary of the form

    {TOKEN_TYPE: callback}

Where callback is of type `f(Token) -> Token`

It only works with the standard and contextual lexers.

### Example 1: Replace string values with ints for INT tokens

```python
from lark import Lark, Token

def tok_to_int(tok):
    return Token.new_borrow_pos(tok.type, int(tok), tok)

parser = Lark("""
start: INT*
%import common.INT
%ignore " "
""", parser="lalr", lexer_callbacks = {'INT': tok_to_int})

print(parser.parse('3 14 159'))
```

Prints out:

```python
Tree(start, [Token(INT, 3), Token(INT, 14), Token(INT, 159)])
```


### Example 2: Collect all comments
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