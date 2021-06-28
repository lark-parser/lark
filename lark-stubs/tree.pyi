# -*- coding: utf-8 -*-

from typing import Literal

class Tree:
    ...

def pydot__tree_to_png(
    tree: Tree,
    filename: str,
    rankdir: Literal["TB", "LR", "BT", "RL"] = ...,
    **kwargs
) -> None:
    ...
