# Features

## Main Features
 - Earley parser, capable of parsing any context-free grammar
   - Implements SPPF, for efficient parsing and storing of ambiguous grammars.
 - LALR(1) parser, limited in power of expression, but very efficient in space and performance (O(n)).
   - Implements a parse-aware lexer that provides a better power of expression than traditional LALR implementations (such as ply).
 - EBNF-inspired grammar, with extra features (See: [Grammar Reference](grammar.md))
 - Builds a parse-tree (AST) automagically based on the grammar
 - Stand-alone parser generator - create a small independent parser to embed in your project. ([read more](tools.html#stand-alone-parser))
 - Flexible error handling by using an interactive parser interface (LALR only)
 - Automatic line & column tracking (for both tokens and matched rules)
 - Automatic terminal collision resolution
  - Warns on regex collisions using the optional `interegular` library. ([read more](how_to_use.html#regex-collisions))
 - Grammar composition - Import terminals and rules from other grammars (see [example](https://github.com/lark-parser/lark/tree/master/examples/composition)).
 - Standard library of terminals (strings, numbers, names, etc.)
 - Unicode fully supported
 - Extensive test suite
 - Type annotations (MyPy support)
 - Pure-Python implementation

[Read more about the parsers](parsers.md)

## Extra features
  - Support for external regex module ([see here](classes.html#using-unicode-character-classes-with-regex))
  - Import grammars from Nearley.js ([read more](tools.html#importing-grammars-from-nearleyjs))
  - CYK parser
  - Visualize your parse trees as dot or png files ([see_example](https://github.com/lark-parser/lark/blob/master/examples/fruitflies.py))
  - Automatic reconstruction of input from parse-tree (see [example](https://github.com/lark-parser/lark/blob/master/examples/advanced/reconstruct_json.py) and [another example](https://github.com/lark-parser/lark/blob/master/examples/advanced/reconstruct_python.py))
  - Use Lark grammars in [Julia](https://github.com/jamesrhester/Lerche.jl) and [Javascript](https://github.com/lark-parser/Lark.js).
