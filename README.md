# Lark - a modern parsing library

Lark is a modern general-purpose parsing library for Python.

It's intended for everyone, from complete beginners to experts in parsing.

Lark focuses on simplicity, power, and speed. It lets you choose between two parsing algorithms:

 - Earley : Parses all context-free grammars (even ambiguous ones)! It is the default.
 - LALR(1): Only LR grammars. Outperforms PLY and most (if not all) other pure-python parsing libraries.

Both algorithms are written in Python and can be used interchangeably with the same grammar\*. Similarly, the lexer can be turned on/off without changing the grammar. That means you can write your parser without any limitations (just keep it context-free) and optimize it for speed only when you need to.

Lark can automagically build an AST from your grammar, without any more code on your part.

\* *Both the lexer and the LALR algorithm require certain limitations on the grammar. If you choose to use them, it's better to learn what they are first.*

### Hello World

Here is a little program to parse "Hello, World!" (Or any other similar phrase):

```python
from lark import Lark
l = Lark('''start: WORD "," WORD "!"
            %import common.WORD
            %ignore " "
         ''')
print( l.parse("Hello, World!") )
```

And the output is:

```python
Tree(start, [Token(WORD, 'Hello'), Token(WORD, 'World')])
```

Notice punctuation doesn't appear in the resulting tree. It's automatically filtered away by Lark.

### Tiny Calculator

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
                 %import common.WS
                 %ignore WS
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

### Fruit Flies Like Bananas

Lark can automatically resolve ambiguity by choosing the simplest solution. Or, you can ask it to return all the possible parse trees, wrapped in a meta "\_ambig" node.

Here's a toy example to parse the famously ambiguous phrase: "fruit flies like bananas"

```python
from lark import Lark

grammar = """
    sentence: noun verb noun        -> simple
            | noun verb "like" noun -> comparative

    noun: adj? NOUN
    verb: VERB
    adj: ADJ

    NOUN: "flies" | "bananas" | "fruit"
    VERB: "like" | "flies"
    ADJ: "fruit"

    %import common.WS
    %ignore WS
"""

parser = Lark(grammar, start='sentence', ambiguity='explicit')  # Explicit ambiguity in parse tree!

tree = parser.parse('fruit flies like bananas')

from lark.tree import pydot__tree_to_png    # Just a neat utility function
pydot__tree_to_png(tree, "examples/fruitflies.png")
```
![fruitflies.png](examples/fruitflies.png)


## Learn more about using Lark

 - **Read the [tutorial](/docs/json_tutorial.md)**, which shows how to write a JSON parser in Lark.
 - Read a blog post: [How to write a DSL with Lark](http://blog.erezsh.com/how-to-write-a-dsl-in-python-with-lark/)
 - Read the [reference](/docs/reference.md)
 - Browse the [examples](/examples), which include a calculator, and a Python-code parser.
 - Check out the [tests](/tests/test_parser.py) for more examples.

### Install Lark

    $ pip install lark-parser

Lark has no dependencies.

### Projects using Lark

 - [mappyfile](https://github.com/geographika/mappyfile) - a MapFile parser for working with MapServer configuration
 - [pytreeview](https://gitlab.com/parmenti/pytreeview) - a lightweight tree-based grammar explorer

Using Lark? Send me a message and I'll add your project!

### How to use Nearley grammars in Lark

Lark comes with a tool to convert grammars from [Nearley](https://github.com/Hardmath123/nearley), a popular Earley library for Javascript. It uses [Js2Py](https://github.com/PiotrDabkowski/Js2Py) to convert and run the Javascript postprocessing code segments.

Here's an example:
```bash
git clone https://github.com/Hardmath123/nearley
python -m lark.tools.nearley nearley/examples/calculator/arithmetic.ne main nearley > ncalc.py
```

You can use the output as a regular python module:

```python
>>> import ncalc
>>> ncalc.parse('sin(pi/4) ^ e')
0.38981434460254655
```

## List of Features

 - **Earley** parser
    - Can parse *ALL* context-free grammars
    - Accepts and resolves ambiguous grammars using a parse forest
    - Optional lexer
 - **LALR(1)** parser
    - Standard & Contextual lexers
 - **EBNF** grammar (with a little extra)
 - Builds a parse-tree (AST) automagically based on the grammar
 - Lexer with regular expressions (regexps)
     - Automatic line & column tracking
     - Automatic token collision resolution (unless both terminals are regexps)
 - **Standard library** of terminals (strings, numbers, names, etc.)
 - Automatic reconstruction of input (experimental, see examples)
 - **Unicode** fully supported
 - Extensive test suite
 - **Python 2 & 3** compatible

[![codecov](https://codecov.io/gh/erezsh/lark/branch/master/graph/badge.svg)](https://codecov.io/gh/erezsh/lark)
[![Build Status](https://travis-ci.org/erezsh/lark.svg?branch=master)](https://travis-ci.org/erezsh/lark)

### Coming soon

These features are planned to be implemented in the near future:

 - Grammar composition
 - Optimizations in both the parsers and the lexer
 - Better ambiguity resolution

### Planned

These features may be implemented some day:

 - Parser generator - create a small parser, independent of Lark, to embed in your project.
    - Generate code in other languages than Python
 - LALR(k) parser
 - "Look-back" Enhancement for LALR(1)
 - Full regexp-collision support using NFAs
 - Automatically produce syntax-highlighters for popular IDEs

## Comparison to other parsers

### Lark does things a little differently

1. *Separates code from grammar*: Parsers written this way are cleaner and easier to read & work with.

2. *Automatically builds a parse tree (AST)*: Trees are always simpler to work with than state-machines. (But if you want to provide a callback for efficiency reasons, Lark lets you do that too)

3. *Follows Python's Idioms*: Beautiful is better than ugly. Readability counts.


### Lark is easier to use

- You can work with parse-trees instead of state-machines
- The grammar is simple to read and write
- There are no restrictions on grammar structure. Any grammar you write can be parsed.
    - Some structures are faster than others. If you care about speed, you can learn them gradually while the parser is already working
    - A well-written grammar is very fast
    - Note: Nondeterminstic grammars will run a little slower
    - Note: Ambiguous grammars (grammars that can be parsed in more than one way) are supported, but may cause significant slowdown if the ambiguity is too big)
- You don't have to worry about terminals (regexps) or rules colliding
- You can repeat expressions without losing efficiency (turns out that's a thing)

### Performance comparison

| Code | CPython Time | PyPy Time | CPython Mem | PyPy Mem
|:-----|:-------------|:------------|:----------|:---------
| **Lark - LALR(1)** | 4.7s | 1.2s | 70M | 134M |
| PyParsing | 32s | 3.5s | 443M | 225M |
| funcparserlib | 8.5s | 1.3s | 483M | 293M |
| Parsimonious | | 5.7s | | 1545M |

Check out the [JSON tutorial](/docs/json_tutorial.md#conclusion) for more details on how the comparison was made.


### Feature comparison

| Library | Algorithm | LOC | Grammar | Builds tree?
|:--------|:----------|:----|:--------|:------------
| **Lark** | Earley/LALR(1) | 0.5K | EBNF+ | Yes! |
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

Lark uses the [MIT license](LICENSE).

## Contribute

Lark is currently accepting pull-requests.

There are many ways you can help the project:

* Improve the performance of Lark's parsing algorithm
* Implement macros for grammars (important for grammar composition)
* Write new grammars for Lark's library
* Write & improve the documentation
* Write a blog post introducing Lark to your audience

If you're interested in taking one of these on, let me know and I will provide more details and assist you in the process.

## Contact

If you have any questions or want my assistance, you can email me at erezshin at gmail com.

I'm also available for contract work.
