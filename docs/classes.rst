API Reference
=============

Lark
----

.. autoclass:: lark.Lark
    :members: open, parse, save, load


Using Unicode character classes with ``regex``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Python's builtin ``re`` module has a few persistent known bugs and also won't parse
advanced regex features such as character classes.
With ``pip install lark-parser[regex]``, the ``regex`` module will be
installed alongside lark and can act as a drop-in replacement to ``re``.

Any instance of Lark instantiated with ``regex=True`` will use the ``regex`` module instead of ``re``.

For example, we can use character classes to match PEP-3131 compliant Python identifiers:

::

    from lark import Lark
    >>> g = Lark(r"""
                        ?start: NAME
                        NAME: ID_START ID_CONTINUE*
                        ID_START: /[\p{Lu}\p{Ll}\p{Lt}\p{Lm}\p{Lo}\p{Nl}_]+/
                        ID_CONTINUE: ID_START | /[\p{Mn}\p{Mc}\p{Nd}\p{Pc}·]+/
                    """, regex=True)

    >>> g.parse('வணக்கம்')
    'வணக்கம்'


Tree
----

.. autoclass:: lark.Tree
    :members: pretty, find_pred, find_data, iter_subtrees, scan_values,
        iter_subtrees_topdown

Token
-----

.. autoclass:: lark.Token

Transformer, Visitor & Interpreter
----------------------------------

See :doc:`visitors`.

ForestVisitor, ForestTransformer, & TreeForestTransformer
-----------------------------------------------------------

See :doc:`forest`.

UnexpectedInput
---------------

.. autoclass:: lark.exceptions.UnexpectedInput
    :members: get_context, match_examples

.. autoclass:: lark.exceptions.UnexpectedToken

.. autoclass:: lark.exceptions.UnexpectedCharacters

InteractiveParser
-----------------

.. autoclass:: lark.parsers.lalr_interactive_parser.InteractiveParser
    :members: choices, feed_token, copy, pretty, resume_parse, exhaust_lexer, accepts

.. autoclass:: lark.parsers.lalr_interactive_parser.ImmutableInteractiveParser
    :members: choices, feed_token, copy, pretty, resume_parse, exhaust_lexer, accepts