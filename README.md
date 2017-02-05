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


## Features

 - EBNF grammar with a little extra
 - Earley & LALR(1)
 - Builds an AST automagically based on the grammar
 - Python 2 & 3 compatible
 - Supports unicode

## License

Lark uses the GPL3 license.

## Contact

If you have any questions or want to contribute, please email me at erezshin at gmail com.
