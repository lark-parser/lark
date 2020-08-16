.. Lark documentation master file, created by
   sphinx-quickstart on Sun Aug 16 13:09:41 2020.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to Lark's documentation!
================================

.. toctree::
   :maxdepth: 2
   :hidden:

   philosophy
   features
   parsers

.. toctree::
   :maxdepth: 2
   :caption: Tutorials & Guides
   :hidden:

   json_tutorial
   how_to_use
   how_to_develop
   nearley
   recipes


.. toctree::
   :maxdepth: 2
   :caption: Reference
   :hidden:

   grammar
   tree_construction
   visitors
   classes


Lark is a modern parsing library for Python. Lark can parse any context-free grammar.

Lark provides:

- Advanced grammar language, based on EBNF
- Three parsing algorithms to choose from: Earley, LALR(1) and CYK
- Automatic tree construction, inferred from your grammar
- Fast unicode lexer with regexp support, and automatic line-counting


**Install Lark**:

.. code:: bash

   $ pip install lark-parser

**Syntax Highlighting**:

-  `Sublime Text & TextMate`_
-  `Visual Studio Code`_ (Or install through the vscode plugin system)
-  `Intellij & PyCharm`_

.. _Sublime Text & TextMate: https://github.com/lark-parser/lark_syntax
.. _Visual Studio Code: https://github.com/lark-parser/vscode-lark
.. _Intellij & PyCharm: https://github.com/lark-parser/intellij-syntax-highlighting