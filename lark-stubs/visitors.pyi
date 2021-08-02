# -*- coding: utf-8 -*-

from typing import TypeVar, Tuple, List, Callable, Generic, Type, Union
from abc import ABC
from .tree import Tree

_T = TypeVar('_T')
_R = TypeVar('_R')
_FUNC = Callable[..., _T]
_DECORATED = Union[_FUNC, type]


class Transformer(ABC, Generic[_T]):

    def __init__(self, visit_tokens: bool = True) -> None:
        ...

    def transform(self, tree: Tree) -> _T:
        ...

    def __mul__(self, other: Transformer[_T]) -> TransformerChain[_T]:
        ...


class TransformerChain(Generic[_T]):
    transformers: Tuple[Transformer[_T], ...]

    def __init__(self, *transformers: Transformer[_T]) -> None:
        ...

    def transform(self, tree: Tree) -> _T:
        ...

    def __mul__(self, other: Transformer[_T]) -> TransformerChain[_T]:
        ...


class Transformer_InPlace(Transformer):
    pass


class Transformer_NonRecursive(Transformer):
    pass


class Transformer_InPlaceRecursive(Transformer):
    pass


class VisitorBase:
    pass


class Visitor(VisitorBase, ABC, Generic[_T]):

    def visit(self, tree: Tree) -> Tree:
        ...

    def visit_topdown(self, tree: Tree) -> Tree:
        ...


class Visitor_Recursive(VisitorBase):

    def visit(self, tree: Tree) -> Tree:
        ...

    def visit_topdown(self, tree: Tree) -> Tree:
        ...


class Interpreter(ABC, Generic[_T]):

    def visit(self, tree: Tree) -> _T:
        ...

    def visit_children(self, tree: Tree) -> List[_T]:
        ...


_InterMethod = Callable[[Type[Interpreter], _T], _R]


def v_args(
        inline: bool = False,
        meta: bool = False,
        tree: bool = False,
        wrapper: Callable = None
) -> Callable[[_DECORATED], _DECORATED]:
    ...


def visit_children_decor(func: _InterMethod) -> _InterMethod:
    ...


class Discard(Exception):
    pass


# Deprecated
class InlineTransformer:
    pass


# Deprecated
def inline_args(obj: _FUNC) -> _FUNC:
    ...
