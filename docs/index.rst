.. Lark documentation master file, created by
   sphinx-quickstart on Sun Aug 16 13:09:41 2020.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to Lark's documentation!
================================


Lark is a modern parsing library for Python. Lark can parse any context-free grammar.

Lark provides:

- Advanced grammar language, based on EBNF
- Three parsing algorithms to choose from: Earley, LALR(1) and CYK
- Automatic tree construction, inferred from your grammar
- Fast unicode lexer with regexp support, and automatic line-counting

Refer to the section :doc:`features` for more information.


Install Lark
--------------

.. code:: bash

   $ pip install lark


-------

.. toctree::
   :maxdepth: 2
   :caption: First steps

   json_tutorial
   examples/index
   features


.. toctree::
   :maxdepth: 2
   :caption: How-to guides

   recipes
   how_to_use
   how_to_develop


.. toctree::
   :maxdepth: 2
   :caption: Addendum

   philosophy
   parsers
   resources


.. toctree::
   :maxdepth: 2
   :caption: Reference

   grammar
   tree_construction
   classes
   visitors
   forest
   tools
