# Parsers
Lark implements the following parsing algorithms: Earley, LALR(1), and CYK

## Earley

An [Earley Parser](https://www.wikiwand.com/en/Earley_parser) is a chart parser capable of parsing any context-free grammar at O(n^3), and O(n^2) when the grammar is unambiguous. It can parse most LR grammars at O(n). Most programming languages are LR, and can be parsed at a linear time.

Lark's Earley implementation runs on top of a skipping chart parser, which allows it to use regular expressions, instead of matching characters one-by-one. This is a huge improvement to Earley that is unique to Lark. This feature is used by default, but can also be requested explicitly using `lexer='dynamic'`.

It's possible to bypass the dynamic lexing, and use the regular Earley parser with a traditional lexer, that tokenizes as an independent first step. Doing so will provide a speed benefit, but will tokenize without using Earley's ambiguity-resolution ability. So choose this only if you know why! Activate with `lexer='standard'`

**SPPF & Ambiguity resolution**

Lark implements the Shared Packed Parse Forest data-structure for the Earley parser, in order to reduce the space and computation required to handle ambiguous grammars.

You can read more about SPPF [here](https://web.archive.org/web/20191229100607/www.bramvandersanden.com/post/2014/06/shared-packed-parse-forest)

As a result, Lark can efficiently parse and store every ambiguity in the grammar, when using Earley.

Lark provides the following options to combat ambiguity:

1) Lark will choose the best derivation for you (default). Users can choose between different disambiguation strategies, and can prioritize (or demote) individual rules over others, using the rule-priority syntax.

2) Users may choose to receive the set of all possible parse-trees (using ambiguity='explicit'), and choose the best derivation themselves. While simple and flexible, it comes at the cost of space and performance, and so it isn't recommended for highly ambiguous grammars, or very long inputs.

3) As an advanced feature, users may use specialized visitors to iterate the SPPF themselves.

**lexer="dynamic_complete"**

Earley's "dynamic" lexer uses regular expressions in order to tokenize the text. It tries every possible combination of terminals, but it matches each terminal exactly once, returning the longest possible match.

That means, for example, that when `lexer="dynamic"` (which is the default), the terminal `/a+/`, when given the text `"aa"`, will return one result, `aa`, even though `a` would also be correct.

This behavior was chosen because it is much faster, and it is usually what you would expect.

Setting `lexer="dynamic_complete"` instructs the lexer to consider every possible regexp match. This ensures that the parser will consider and resolve every ambiguity, even inside the terminals themselves. This lexer provides the same capabilities as scannerless Earley, but with different performance tradeoffs.

Warning: This lexer can be much slower, especially for open-ended terminals such as `/.*/`


## LALR(1)

[LALR(1)](https://www.wikiwand.com/en/LALR_parser) is a very efficient, true-and-tested parsing algorithm. It's incredibly fast and requires very little memory. It can parse most programming languages (For example: Python and Java).

LALR(1) stands for:

- Left-to-right parsing order

- Rightmost derivation, bottom-up

- Lookahead of 1 token

Lark comes with an efficient implementation that outperforms every other parsing library for Python (including PLY)

Lark extends the traditional YACC-based architecture with a *contextual lexer*, which processes feedback from the parser, making the LALR(1) algorithm stronger than ever.

The contextual lexer communicates with the parser, and uses the parser's lookahead prediction to narrow its choice of terminals. So at each point, the lexer only matches the subgroup of terminals that are legal at that parser state, instead of all of the terminals. It’s surprisingly effective at resolving common terminal collisions, and allows one to parse languages that LALR(1) was previously incapable of parsing.

(If you're familiar with YACC, you can think of it as automatic lexer-states)

This is an improvement to LALR(1) that is unique to Lark.

### Grammar constraints in LALR(1)

Due to having only a lookahead of one token, LALR is limited in its ability to choose between rules, when they both match the input.

Tips for writing a conforming grammar:

- Try to avoid writing different rules that can match the same sequence of characters.

- For the best performance, prefer left-recursion over right-recursion.

- Consider setting terminal priority only as a last resort.

For a better understanding of these constraints, it's recommended to learn how a SLR parser works. SLR is very similar to LALR but much simpler.

## CYK Parser

A [CYK parser](https://www.wikiwand.com/en/CYK_algorithm) can parse any context-free grammar at O(n^3*|G|).

Its too slow to be practical for simple grammars, but it offers good performance for highly ambiguous grammars.
