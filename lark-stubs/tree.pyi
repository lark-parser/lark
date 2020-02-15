# -*- coding: utf-8 -*-

from typing import List, Callable, Iterator, Union, Optional
from .lexer import Token


class Tree:

    data: str
    children: List[Union[str, Tree]]
    meta: Token

    def __init__(self, data: str, children: List[Tree], meta: Optional[Token] = None):
        ...

    def pretty(self, indent_str: str = ...) -> str:
        ...

    def find_pred(self, pred: Callable[[Tree], bool]) -> Iterator[Tree]:
        ...

    def find_data(self, data: str) -> Iterator[Tree]:
        ...

    def iter_subtrees(self) -> Iterator[Tree]:
        ...

    def iter_subtrees_topdown(self) -> Iterator[Tree]:
        ...

    def __eq__(self, other: object) -> bool:
        ...

    def __hash__(self) -> int:
        ...


class SlottedTree(Tree):
    pass
