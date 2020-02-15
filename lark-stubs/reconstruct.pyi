# -*- coding: utf-8 -*-

from .lark import Lark
from .tree import Tree


class Reconstructor:

    def __init__(self, parser: Lark):
        ...

    def reconstruct(self, tree: Tree) -> str:
        ...
