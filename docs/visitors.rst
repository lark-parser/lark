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

Visitors visit each node of the tree, and run the appropriate method on it according to the node's data.

They work bottom-up, starting with the leaves and ending at the root of the tree.

There are two classes that implement the visitor interface:

- ``Visitor``: Visit every node (without recursion)
- ``Visitor_Recursive``: Visit every node using recursion. Slightly faster.

Example:
    ::

        class IncreaseAllNumbers(Visitor):
        def number(self, tree):
            assert tree.data == "number"
            tree.children[0] += 1

        IncreaseAllNumbers().visit(parse_tree)

.. autoclass:: lark.visitors.Visitor

.. autoclass:: lark.visitors.Visitor_Recursive

Interpreter
-----------

.. autoclass:: lark.visitors.Interpreter

Transformer
-----------

.. autoclass:: lark.visitors.Transformer
    :members: __default__, __default_token__

v_args
------

.. autofunction:: lark.visitors.v_args

Discard
-------

.. autoclass:: lark.visitors.Discard