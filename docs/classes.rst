API Reference
=============

Lark
----

.. autoclass:: lark.Lark
    :members: open, parse, save, load

LarkOptions
-----------

.. autoclass:: lark.lark.LarkOptions

Tree
----

.. autoclass:: lark.Tree
    :members: pretty, find_pred, find_data, iter_subtrees,
        iter_subtrees_topdown

Token
-----

.. autoclass:: lark.Token

Transformer, Vistor & Interpretor
---------------------------------

See :doc:`visitors`.

UnexpectedInput
---------------

.. autoclass:: lark.exceptions.UnexpectedInput
    :members: get_context, match_examples

.. autoclass:: lark.exceptions.UnexpectedToken

.. autoclass:: lark.exceptions.UnexpectedCharacters

ParserPuppet
------------

.. autoclass:: lark.parsers.lalr_puppet.ParserPuppet
    :members: choices, feed_token, copy, pretty, resume_parse
