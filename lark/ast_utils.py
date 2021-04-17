"""
    Module of utilities for transforming a lark.Tree into a custom Abstract Syntax Tree
"""

import inspect, re

from lark import Transformer, v_args

class Ast(object):
    """Abstract class

    Subclasses will be collected by `create_transformer()`
    """
    pass

class AsList(object):
    """Abstract class

    Subclasses will be instanciated with the parse results as a single list, instead of as arguments.
    """

def camel_to_snake(name):
    return re.sub(r'(?<!^)(?=[A-Z])', '_', name).lower()

def _call(func, _data, children, _meta):
    return func(*children)

inline = v_args(wrapper=_call)

def create_transformer(ast_module, transformer=None):
    """Collects `Ast` subclasses from the given module, and creates a Lark transformer that builds the AST.

    For each class, we create a corresponding rule in the transformer, with a matching name.
    CamelCase names will be converted into snake_case. Example: "CodeBlock" -> "code_block".

    Classes starting with an underscore (`_`) will be skipped.

    Parameters:
        ast_module - A Python module containing all the subclasses of `ast_utils.Ast`
        transformer (Optional[Transformer]) - An initial transformer. Its attributes may be overwritten.
    """
    t = transformer or Transformer()

    for name, obj in inspect.getmembers(ast_module):
        if not name.startswith('_') and inspect.isclass(obj):
            if issubclass(obj, Ast):
                if not issubclass(obj, AsList):
                    obj = inline(obj).__get__(t)

                setattr(t, camel_to_snake(name), obj)

    return t