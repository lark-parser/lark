# Lark

A modern parsing library for Python

## Overview

Lark can parse any context-free grammar.

Lark provides:

- Advanced grammar language, based on EBNF
- Three parsing algorithms to choose from: Earley, LALR(1) and CYK
- Automatic tree construction, inferred from your grammar
- Fast unicode lexer with regexp support, and automatic line-counting

Lark's code is hosted on Github: [https://github.com/lark-parser/lark](https://github.com/lark-parser/lark)

### Install
```bash
$ pip install lark-parser
```

#### Syntax Highlighting

- [Sublime Text & TextMate](https://github.com/lark-parser/lark_syntax)
- [Visual Studio Code](https://github.com/lark-parser/vscode-lark) (Or install through the vscode plugin system)

-----

## Documentation Index


* [Philosophy & Design Choices](philosophy.md)
* [Full List of Features](features.md)
* [Examples](https://github.com/lark-parser/lark/tree/master/examples)
* Tutorials
    * [How to write a DSL](http://blog.erezsh.com/how-to-write-a-dsl-in-python-with-lark/) - Implements a toy LOGO-like language with an interpreter
    * [How to write a JSON parser](json_tutorial.md)
* Guides
    * [How to use Lark](how_to_use.md)
* Reference
    * [Grammar](grammar.md)
    * [Tree Construction](tree_construction.md)
    * [Classes](classes.md)
    * [Cheatsheet (PDF)](lark_cheatsheet.pdf)
* Discussion
    * [Forum (Google Groups)](https://groups.google.com/forum/#!forum/lark-parser)