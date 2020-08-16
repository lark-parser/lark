Transformers & Visitors
=======================

Transformers & Visitors provide a convenient interface to process the
parse-trees that Lark returns.

They are used by inheriting from the correct class (visitor or transformer),
and implementing methods corresponding to the rule you wish to process. Each
method accepts the children as an argument. That can be modified using the
``v_args`` decorator, which allows to inline the arguments (akin to ``*args``),
or add the tree ``meta`` property as an argument.

See: `visitors.py`_

.. _visitors.py: https://github.com/lark-parser/lark/blob/master/lark/visitors.py

Visitor
-------

.. autoclass:: lark.visitors.VisitorBase

.. autoclass:: lark.visitors.Visitor

.. autoclass:: lark.visitors.Visitor_Recursive


Transformer
-----------

.. autoclass:: lark.visitors.Transformer
    :members: __default__, __default_token__

Interpreter
-----------

.. autoclass:: lark.visitors.Interpreter

v_args
------

.. autofunction:: lark.visitors.v_args

Discard
-------

.. autoclass:: lark.visitors.Discard 