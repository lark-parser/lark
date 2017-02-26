# Lark - a modern parsing library

Lark is a modern general-purpose parsing library for Python.

Lark focuses on simplicity, power, and speed. It lets you choose between two parsing algorithms:

 - Earley : Parses all context-free grammars (even ambiguous ones)! It is the default.
 - LALR(1): Only LR grammars. Outperforms PLY and most (if not all) other pure-python parsing libraries.

Both algorithms are written in Python and can be used interchangeably with the same grammar (aside for algorithmic restrictions). See "Comparison to other parsers" for more details.

Lark can automagically build an AST from your grammar, without any more code on your part.


## Lark does things a little differently

1. *Separates code from grammar*: The result is parsers that are cleaner and easier to read & work with.

2. *Automatically builds a tree (AST)*: Trees are always simpler to work with than state-machines. (But if you want to provide a callback for efficiency reasons, Lark lets you do that too)

3. *Follows Python's Idioms*: Beautiful is better than ugly. Readability counts.

## Hello World

Here is a little program to parse "Hello, World!" (Or any other similar phrase):

```python
from lark import Lark
l = Lark('''start: WORD "," WORD "!"
            WORD: /\w+/
            %ignore " "
         ''')
print( l.parse("Hello, World!") )
```

And the output is:

```python
Tree(start, [Token(WORD, 'Hello'), Token(WORD, 'World')])
```

Notice punctuation doesn't appear in the resulting tree. It's automatically filtered away by Lark.

## Tiny Calculator

```python
from lark import Lark, InlineTransformer
parser = Lark('''?sum: product
                     | sum "+" product   -> add
                     | sum "-" product   -> sub

                 ?product: item
                     | product "*" item  -> mul
                     | product "/" item  -> div

                 ?item: NUMBER           -> number
                      | "-" item         -> neg
                      | "(" sum ")"

                 %import common.NUMBER
                 %ignore /\s+/
         ''', start='sum')

class CalculateTree(InlineTransformer):
    from operator import add, sub, mul, truediv as div, neg
    number = float

def calc(expr):
    return CalculateTree().transform( parser.parse(expr) )
```

In the grammar, we shape the resulting tree. The '->' operator renames branches, and the '?' prefix tells Lark to inline single values. (see the [tutorial](/docs/json_tutorial.md) for a more in-depth explanation)

Then, the transformer calculates the tree and returns a number:

```python
>>> calc("(200 + 3*-3) * 7")
1337.0
```

## Learn more about using Lark

 - **Read the [tutorial](/docs/json_tutorial.md)**, which shows how to write a JSON parser in Lark.
 - Read the [reference](/docs/reference.md)
 - Browse the [examples](/examples), which include a calculator, and a Python-code parser.
 - Check out the [tests](/tests/test_parser.py) for more examples.

## Install Lark

    $ pip install lark-parser

Lark has no dependencies.

## List of Features

 - Python 2 & 3 compatible
 - Earley & LALR(1)
 - EBNF grammar with a little extra
 - Builds an AST automagically based on the grammar
 - Standard library of terminals (strings, numbers, names, etc.)
 - Unicode fully supported
 - Extensive test suite
 - Lexer (optional)
     - Automatic line & column tracking
     - Automatic token collision resolution (unless both terminals are regexps)
     - Contextual lexing for LALR

## Coming soon

These features are planned to be implemented in the near future:

 - Parser generator - create a small parser, independent of Lark, to embed in your project.
 - Grammar composition
 - Optimizations in both the parsers and the lexer
 - Better handling of ambiguity

## Comparison to other parsers

This is a feature comparison. For benchmarks vs other parsers, check out the [JSON tutorial](/docs/json_tutorial.md#conclusion).

| Library | Algorithm | LOC | Grammar | Builds tree?
|:--------|:----------|:----|:--------|:------------
| Lark | Earley/LALR(1) | 0.5K | EBNF+ | Yes! |
| [PLY](http://www.dabeaz.com/ply/) | LALR(1) | 4.6K | Yacc-like BNF | No |
| [PyParsing](http://pyparsing.wikispaces.com/) | PEG | 5.7K | Parser combinators | No |
| [Parsley](https://pypi.python.org/pypi/Parsley) | PEG | 3.3K | EBNF-like | No |
| [funcparserlib](https://github.com/vlasovskikh/funcparserlib) | Recursive-Descent | 0.5K | Parser combinators | No 
| [Parsimonious](https://github.com/erikrose/parsimonious) | PEG | ? | EBNF | Yes |

(*LOC measures lines of code of the parsing algorithm(s), without accompanying files*)

It's hard to compare parsers with different parsing algorithms, since each algorithm has many advantages and disadvantages. However, I will try to summarize the main points here:

- **Earley**: The most powerful context-free algorithm. It can parse all context-free grammars, and it's Big-O efficient. But, its constant-time performance is slow.
- **LALR(1)**: The fastest, most efficient algorithm. It runs at O(n) and uses the least amount of memory. But while it can parse most programming languages, there are many grammars it can't handle.
- **PEG**: A powerful algorithm that can parse all deterministic context-free grammars\* at O(n). But, it hides ambiguity, and takes a lot of memory to run.
- **Recursive-Descent**: Fast for simple grammars, and simple to implement. But poor in Big-O complexity.

Lark offers both Earley and LALR(1), which means you can choose between the most powerful and the most efficient algorithms, without having to change libraries.

(\* *According to Wikipedia, it remains unanswered whether PEGs can really parse all deterministic CFGs*)

## License

Lark uses the MIT license.

## Contact

If you have any questions or want to contribute, please email me at erezshin at gmail com.
