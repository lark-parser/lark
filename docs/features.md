# Features

 - EBNF-inspired grammar, with extra features (See: [Grammar Reference](grammar.md))
 - Builds a parse-tree (AST) automagically based on the grammar 
 - Stand-alone parser generator - create a small independent parser to embed in your project.
 - Automatic line & column tracking
 - Automatic terminal collision resolution
 - Standard library of terminals (strings, numbers, names, etc.)
 - Unicode fully supported
 - Extensive test suite
 - Python 2 & Python 3 compatible
 - Pure-Python implementation

## Parsers

Lark implements the following parsing algorithms:

### Earley

An [Earley Parser](https://www.wikiwand.com/en/Earley_parser) is a chart parser capable of parsing any context-free grammar at O(n^3), and O(n^2) when the grammar is unambiguous. It can parse most LR grammars at O(n). Most programming languages are LR, and can be parsed at a linear time.

Lark's Earley implementation runs on top of a skipping chart parser, which allows it to use regular expressions, instead of matching characters one-by-one. This is a huge improvement to Earley that is unique to Lark. This feature is used by default, but can also be requested explicitely using `lexer='dynamic'`.

It's possible to bypass the dynamic lexer, and use the regular Earley parser with a traditional lexer, that tokenizes as an independant first step. Doing so will provide a speed benefit, but will tokenize without using Earley's ambiguity-resolution ability. So choose this only if you know why! Activate with `lexer='standard'`

**Note on ambiguity**

Lark by default can handle any ambiguity in the grammar (Earley+dynamic). The user may request to recieve all derivations (using ambiguity='explicit'), or let Lark automatically choose the most fitting derivation (default behavior).

Lark also supports user-defined rule priority to steer the automatic ambiguity resolution.

### LALR(1)

[LALR(1)](https://www.wikiwand.com/en/LALR_parser) is a very efficient, true-and-tested parsing algorithm. It's incredibly fast and requires very little memory. It can parse most programming languages (For example: Python and Java).

Lark comes with an efficient implementation that outperforms every other parsing library for Python (including PLY)

Lark extends the traditional YACC-based architecture with a *contextual lexer*, which automatically provides feedback from the parser to the lexer, making the LALR(1) algorithm stronger than ever.

The contextual lexer communicates with the parser, and uses the parser's lookahead prediction to narrow its choice of tokens. So at each point, the lexer only matches the subgroup of terminals that are legal at that parser state, instead of all of the terminals. It’s surprisingly effective at resolving common terminal collisions, and allows to parse languages that LALR(1) was previously incapable of parsing.

This is an improvement to LALR(1) that is unique to Lark. 

### CYK Parser

A [CYK parser](https://www.wikiwand.com/en/CYK_algorithm) can parse any context-free grammar at O(n^3*|G|). 

Its too slow to be practical for simple grammars, but it offers good performance for highly ambiguous grammars.

# Other features

  - Import grammars from Nearley.js

### Experimental features
  - Automatic reconstruction of input from parse-tree (see examples)

### Planned features (not implemented yet)
 - Generate code in other languages than Python
 - Grammar composition
 - LALR(k) parser
 - Full regexp-collision support using NFAs
 - Automatically produce syntax-highlighters for grammars, for popular IDEs
