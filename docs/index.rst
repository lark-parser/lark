.. Lark documentation master file, created by
   sphinx-quickstart on Sun Aug 16 13:09:41 2020.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to Lark's documentation!
================================

.. toctree::
   :maxdepth: 2
   :caption: Overview
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
   recipes
   examples/index


.. toctree::
   :maxdepth: 2
   :caption: Reference
   :hidden:

   grammar
   tree_construction
   classes
   visitors
   forest
   nearley



Lark is a modern parsing library for Python. Lark can parse any context-free grammar.

Lark provides:

- Advanced grammar language, based on EBNF
- Three parsing algorithms to choose from: Earley, LALR(1) and CYK
- Automatic tree construction, inferred from your grammar
- Fast unicode lexer with regexp support, and automatic line-counting


Install Lark
--------------

.. code:: bash

   $ pip install lark-parser

Syntax Highlighting
-------------------

-  `Sublime Text & TextMate`_
-  `Visual Studio Code`_ (Or install through the vscode plugin system)
-  `Intellij & PyCharm`_
-  `Vim`_
-  `Atom`_

.. _Sublime Text & TextMate: https://github.com/lark-parser/lark_syntax
.. _Visual Studio Code: https://github.com/lark-parser/vscode-lark
.. _Intellij & PyCharm: https://github.com/lark-parser/intellij-syntax-highlighting
.. _Vim: https://github.com/lark-parser/vim-lark-syntax
.. _Atom: https://github.com/Alhadis/language-grammars

Resources
---------

-  :doc:`philosophy`
-  :doc:`features`
-  `Examples`_
-  `Online IDE`_
-  Tutorials

   -  `How to write a DSL`_ - Implements a toy LOGO-like language with
      an interpreter
   -  :doc:`json_tutorial` - Teaches you how to use Lark
   -  Unofficial

      -  `Program Synthesis is Possible`_ - Creates a DSL for Z3

-  Guides

   -  :doc:`how_to_use`
   -  :doc:`how_to_develop`

-  Reference

   -  :doc:`grammar`
   -  :doc:`tree_construction`
   -  :doc:`visitors`
   -  :doc:`forest`
   -  :doc:`classes`
   -  :doc:`nearley`
   -  `Cheatsheet (PDF)`_

-  Discussion

   -  `Gitter`_
   -  `Forum (Google Groups)`_


.. _Examples: https://github.com/lark-parser/lark/tree/master/examples
.. _Online IDE: https://lark-parser.github.io/lark/ide/app.html
.. _How to write a DSL: http://blog.erezsh.com/how-to-write-a-dsl-in-python-with-lark/
.. _Program Synthesis is Possible: https://www.cs.cornell.edu/~asampson/blog/minisynth.html
.. _Cheatsheet (PDF): _static/lark_cheatsheet.pdf
.. _Gitter: https://gitter.im/lark-parser/Lobby
.. _Forum (Google Groups): https://groups.google.com/forum/#!forum/lark-parser
