Examples for Lark
=================

How to run the examples
^^^^^^^^^^^^^^^^^^^^^^^

After cloning the repo, open the terminal into the root directory of the
project, and run the following:

.. code:: bash

   [lark]$ python -m examples.<name_of_example>

For example, the following will parse all the Python files in the
standard library of your local installation:

.. code:: bash

   [lark]$ python -m examples.python_parser

Beginners
~~~~~~~~~

-  `calc.py`_ - A simple example of a REPL calculator
-  `json_parser.py`_ - A simple JSON parser (comes with a tutorial, see
   docs)
-  `indented_tree.py`_ - A demonstration of parsing indentation
   (“whitespace significant” language)
-  `fruitflies.py`_ - A demonstration of ambiguity
-  `turtle_dsl.py`_ - Implements a LOGO-like toy language for Python’s
   turtle, with interpreter.
-  `lark_grammar.py`_ + `lark.lark`_ - A reference implementation of the
   Lark grammar (using LALR(1) + standard lexer)

Advanced
~~~~~~~~

-  `error_reporting_lalr.py`_ - A demonstration of example-driven error
   reporting with the LALR parser
-  `python_parser.py`_ - A fully-working Python 2 & 3 parser (but not
   production ready yet!)
-  `python_bytecode.py`_ - A toy example showing how to compile Python
   directly to bytecode
-  `conf_lalr.py`_ - Demonstrates the power of LALR’s contextual lexer
   on a toy configuration language
-  `conf_earley.py`_ - Demonstrates the power of Earley’s dynamic lexer
   on a toy configuration language
-  `custom_lexer.py`_ - Demonstrates using a custom lexer to parse a
   non-textual stream of data
-  `reconstruct_json.py`_ - Demonstrates the experimental
   text-reconstruction feature

.. _calc.py: calc.py
.. _json_parser.py: json_parser.py
.. _indented_tree.py: indented_tree.py
.. _fruitflies.py: fruitflies.py
.. _turtle_dsl.py: turtle_dsl.py
.. _lark_grammar.py: lark_grammar.py
.. _lark.lark: lark.lark
.. _error_reporting_lalr.py: error_reporting_lalr.py
.. _python_parser.py: python_parser.py
.. _python_bytecode.py: python_bytecode.py
.. _conf_lalr.py: conf_lalr.py
.. _conf_earley.py: conf_earley.py
.. _custom_lexer.py: custom_lexer.py
.. _reconstruct_json.py: reconstruct_json.py