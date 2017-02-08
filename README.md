# Lark - a modern pure-Python parsing library

Lark is a modern general-purpose Python parsing library, that focuses on simplicity and power.

Lark accepts grammars as EBNF and lets you choose between two parsing algorithms:

 - Earley : Parses all context-free grammars (even ambiguous ones)!
 - LALR(1): Only LR grammars. Outperforms PLY and most if not all other pure-python parsing libraries.

Both algorithms are pure-python implementations and can be used interchangably (aside for algorithmic restrictions).

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
            SPACE.ignore: " "
         ''')
print( l.parse("Hello, World!") )
```

And the output is:

```python
Tree(start, [Token(WORD, Hello), Token(WORD, World)])
```

Notice punctuation doesn't appear in the resulting tree. It's automatically filtered away by Lark.

To learn more about Lark:
 - Learn how to parse json at the [tutorial](/docs/json_tutorial.md)

## Features

 - EBNF grammar with a little extra
 - Earley & LALR(1)
 - Builds an AST automagically based on the grammar
 - Automatic line & column tracking
 - Automatic token collision resolution (unless both tokens are regexps)
 - Python 2 & 3 compatible
 - Unicode fully supported

## Coming soon

These features are planned to be implemented in the near future:

 - Grammar composition (in cases that the tokens can reliably signify a grammar change)
 - Parser generator - create a small parser, indepdendent of Lark, to embed in your project.

## Comparison to other parsers

| Library | Algorithm | LOC | Grammar | Builds AST
|:--------|:----------|:----|:--------|:------------
| Lark | Earley/LALR(1) | 0.5K | EBNF+ | Yes! |
| [PLY](http://www.dabeaz.com/ply/) | LALR(1) | 4.6K | Yacc-like BNF | No |
| [PyParsing](http://pyparsing.wikispaces.com/) | PEG | 5.7K | Parser combinators | No |
| [Parsley](https://pypi.python.org/pypi/Parsley) | PEG | 3.3K | EBNF-like | No |
| [funcparselib](https://github.com/vlasovskikh/funcparserlib) | Recursive-Descent | 0.5K | Parser combinators | No |

(*LOC measures lines of code of the parsing algorithm(s), without accompanying files*)

It's hard to compare parsers with different parsing algorithms, since each algorithm has many advantages and disadvantages. However, I will try to summarize the main points here:

- **Earley**: The most powerful context-free algorithm. It can parse all context-free grammars, and it's Big-O efficient. But, its constant-time performance is slow.
- **LALR(1)**: The fastest, most efficient algorithm. It runs at O(n) and uses the least amount of memory. But while it can parse most programming languages, there are many grammars it can't handle.
- **PEG**: A powerful algorithm that can parse all deterministic context-free grammars\* at O(n). But, it hides ambiguity, and takes a lot of memory to run.
- **Recursive-Descent**: Fast for simple grammars, and simple to implement. But poor in Big-O complexity.

Lark offers both Earley and LALR(1), which means you can choose between the most powerful and the most efficient algorithms, without having to change libraries.

(\* *According to Wikipedia, it remains unanswered whether PEGs can really parse all deterministic CFGs*)

## License

Lark uses the GPL3 license.

## Contact

If you have any questions or want to contribute, please email me at erezshin at gmail com.
