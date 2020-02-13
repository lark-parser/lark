
Lark implements the following parsing algorithms: Earley, LALR(1), and CYK

# Earley

An [Earley Parser](https://www.wikiwand.com/en/Earley_parser) is a chart parser capable of parsing any context-free grammar at O(n^3), and O(n^2) when the grammar is unambiguous. It can parse most LR grammars at O(n). Most programming languages are LR, and can be parsed at a linear time.

Lark's Earley implementation runs on top of a skipping chart parser, which allows it to use regular expressions, instead of matching characters one-by-one. This is a huge improvement to Earley that is unique to Lark. This feature is used by default, but can also be requested explicitly using `lexer='dynamic'`.

It's possible to bypass the dynamic lexing, and use the regular Earley parser with a traditional lexer, that tokenizes as an independent first step. Doing so will provide a speed benefit, but will tokenize without using Earley's ambiguity-resolution ability. So choose this only if you know why! Activate with `lexer='standard'`

**SPPF & Ambiguity resolution**

Lark implements the Shared Packed Parse Forest data-structure for the Earley parser, in order to reduce the space and computation required to handle ambiguous grammars.

You can read more about SPPF [here](http://www.bramvandersanden.com/post/2014/06/shared-packed-parse-forest/)

As a result, Lark can efficiently parse and store every ambiguity in the grammar, when using Earley.

Lark provides the following options to combat ambiguity:

1) Lark will choose the best derivation for you (default). Users can choose between different disambiguation strategies, and can prioritize (or demote) individual rules over others, using the rule-priority syntax.

2) Users may choose to receive the set of all possible parse-trees (using ambiguity='explicit'), and choose the best derivation themselves. While simple and flexible, it comes at the cost of space and performance, and so it isn't recommended for highly ambiguous grammars, or very long inputs.

3) As an advanced feature, users may use specialized visitors to iterate the SPPF themselves. Future versions of Lark intend to improve and simplify this interface.


**dynamic_complete**

**TODO: Add documentation on dynamic_complete**

# LALR(1)

[LALR(1)](https://www.wikiwand.com/en/LALR_parser) is a very efficient, true-and-tested parsing algorithm. It's incredibly fast and requires very little memory. It can parse most programming languages (For example: Python and Java).

Lark comes with an efficient implementation that outperforms every other parsing library for Python (including PLY)

Lark extends the traditional YACC-based architecture with a *contextual lexer*, which automatically provides feedback from the parser to the lexer, making the LALR(1) algorithm stronger than ever.

The contextual lexer communicates with the parser, and uses the parser's lookahead prediction to narrow its choice of tokens. So at each point, the lexer only matches the subgroup of terminals that are legal at that parser state, instead of all of the terminals. It’s surprisingly effective at resolving common terminal collisions, and allows to parse languages that LALR(1) was previously incapable of parsing.

This is an improvement to LALR(1) that is unique to Lark.

# CYK Parser

A [CYK parser](https://www.wikiwand.com/en/CYK_algorithm) can parse any context-free grammar at O(n^3*|G|).

Its too slow to be practical for simple grammars, but it offers good performance for highly ambiguous grammars.
