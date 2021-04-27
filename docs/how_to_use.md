# How To Use Lark - Guide

## Work process

This is the recommended process for working with Lark:

1. Collect or create input samples, that demonstrate key features or behaviors in the language you're trying to parse.

2. Write a grammar. Try to aim for a structure that is intuitive, and in a way that imitates how you would explain your language to a fellow human.

3. Try your grammar in Lark against each input sample. Make sure the resulting parse-trees make sense.

4. Use Lark's grammar features to [shape the tree](tree_construction.md): Get rid of superfluous rules by inlining them, and use aliases when specific cases need clarification.

  - You can perform steps 1-4 repeatedly, gradually growing your grammar to include more sentences.

5. Create a transformer to evaluate the parse-tree into a structure you'll be comfortable to work with. This may include evaluating literals, merging branches, or even converting the entire tree into your own set of AST classes.

Of course, some specific use-cases may deviate from this process. Feel free to suggest these cases, and I'll add them to this page.

## Getting started

Browse the [Examples](https://github.com/lark-parser/lark/tree/master/examples) to find a template that suits your purposes.

Read the tutorials to get a better understanding of how everything works. (links in the [main page](/index))

Use the [Cheatsheet (PDF)](https://lark-parser.readthedocs.io/en/latest/_static/lark_cheatsheet.pdf) for quick reference.

Use the reference pages for more in-depth explanations. (links in the [main page](/index))

## Debug

Grammars may contain non-obvious bugs, usually caused by rules or terminals interfering with each other in subtle ways.

When trying to debug a misbehaving grammar, the following methodology is recommended:

1. Create a copy of the grammar, so you can change the parser/grammar without any worries
2. Find the minimal input that creates the error
3. Slowly remove rules from the grammar, while making sure the error still occurs.

Usually, by the time you get to a minimal grammar, the problem becomes clear.

But if it doesn't, feel free to ask us on gitter, or even open an issue. Post a reproducing code, with the minimal grammar and input, and we'll do our best to help.

### LALR

By default Lark silently resolves Shift/Reduce conflicts as Shift. To enable warnings pass `debug=True`. To get the messages printed you have to configure the `logger` beforehand. For example:

```python
import logging
from lark import Lark, logger

logger.setLevel(logging.DEBUG)

collision_grammar = '''
start: as as
as: a*
a: "a"
'''
p = Lark(collision_grammar, parser='lalr', debug=True)
```

## Tools

### Stand-alone parser

Lark can generate a stand-alone LALR(1) parser from a grammar.

The resulting module provides the same interface as Lark, but with a fixed grammar, and reduced functionality.

Run using:

```bash
python -m lark.tools.standalone
```

For a play-by-play, read the [tutorial](http://blog.erezsh.com/create-a-stand-alone-lalr1-parser-in-python/)

### Import Nearley.js grammars

It is possible to import Nearley grammars into Lark. The Javascript code is translated using Js2Py.

Read the [reference page](nearley.md)
