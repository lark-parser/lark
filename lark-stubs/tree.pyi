# -*- coding: utf-8 -*-

from typing import List, Callable, Iterator, Union, Optional, Literal, Any
from .lexer import TerminalDef

class Meta:
    empty: bool
    line: int
    column: int
    start_pos: int
    end_line: int
    end_column: int
    end_pos: int
    orig_expansion: List[TerminalDef]
    match_tree: bool


class Tree:
    data: str
    children: List[Union[str, Tree]]
    meta: Meta

    def __init__(
        self,
        data: str,
        children: List[Union[str, Tree]],
        meta: Optional[Meta] = None
    ) -> None:
        ...

    def pretty(self, indent_str: str = ...) -> str:
        ...

    def find_pred(self, pred: Callable[[Tree], bool]) -> Iterator[Tree]:
        ...

    def find_data(self, data: str) -> Iterator[Tree]:
        ...

    def expand_kids_by_index(self, *indices: int) -> None:
        ...

    def scan_values(self, pred: Callable[[Union[str, Tree]], bool]) -> List[str]:
        ...

    def iter_subtrees(self) -> Iterator[Tree]:
        ...

    def iter_subtrees_topdown(self) -> Iterator[Tree]:
        ...

    def copy(self) -> Tree:
        ...

    def set(self, data: str, children: List[Union[str, Tree]]) -> None:
        ...

    def __hash__(self) -> int:
        ...


class SlottedTree(Tree):
    pass


def pydot__tree_to_png(
    tree: Tree,
    filename: str,
    rankdir: Literal["TB", "LR", "BT", "RL"] = ...,
    **kwargs
) -> None:
    ...
