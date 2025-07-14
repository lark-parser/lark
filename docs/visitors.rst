Transformers & Visitors
=======================

Transformers & Visitors provide a convenient interface to process the
parse-trees that Lark returns.

They are used by inheriting from one of the classes described here,
and implementing methods corresponding to the rule you wish to process. Each
method accepts the children as an argument. That can be modified using the
``v_args`` decorator, which allows one to inline the arguments (akin to ``*args``),
or add the tree ``meta`` property as an argument.

See: `visitors.py`_

.. _visitors.py: https://github.com/lark-parser/lark/blob/master/lark/visitors.py

Visitor
-------

Visitors visit each node of the tree and run the appropriate method on it according to the node's data.
They can work top-down or bottom-up, depending on what method you use.

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
    :members: visit, visit_topdown, __default__

.. autoclass:: lark.visitors.Visitor_Recursive
    :members: visit, visit_topdown, __default__

Interpreter
-----------

Example:
    ::

        from lark.visitors import Interpreter


        class IncreaseSomeOfTheNumbers(Interpreter):
            def number(self, tree):
                tree.children[0] += 1

            def skip(self, tree):
                # skip this subtree. don't change any number node inside it.
                pass


        IncreaseSomeOfTheNumbers().visit(parse_tree)


.. autoclass:: lark.visitors.Interpreter
    :members: visit, visit_children, __default__

Transformer
-----------

.. autoclass:: lark.visitors.Transformer
    :members: transform, __default__, __default_token__, __mul__

Example:
    ::

        from lark import Tree, Transformer

        class EvalExpressions(Transformer):
            def expr(self, args):
                    return eval(args[0])

        t = Tree('a', [Tree('expr', ['1+2'])])
        print(EvalExpressions().transform( t ))

        # Prints: Tree(a, [3])

Example:
    ::

        class T(Transformer):
            INT = int
            NUMBER = float
            def NAME(self, name):
                return lookup_dict.get(name, name)

        T(visit_tokens=True).transform(tree)

.. autoclass:: lark.visitors.Transformer_NonRecursive

.. autoclass:: lark.visitors.Transformer_InPlace

.. autoclass:: lark.visitors.Transformer_InPlaceRecursive

Useful Utilities
----------------

.. autofunction:: lark.visitors.v_args
.. autofunction:: lark.visitors.visit_children_decor
.. autofunction:: lark.visitors.merge_transformers

Discard
-------

``Discard`` is the singleton instance of ``_DiscardType``.

.. autoclass:: lark.visitors._DiscardType


VisitError
----------

.. autoclass:: lark.exceptions.VisitError
