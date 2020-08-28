# -*- coding: utf-8 -*-

from typing import List, Dict, Union
from .lark import Lark
from .tree import Tree
from .visitors import Transformer_InPlace
from .lexer import TerminalDef


class WriteTokensTransformer(Transformer_InPlace):

    def __init__(self, tokens: Dict[str, TerminalDef], term_subs):
        ...


class MatchTree(Tree):
    pass


class MakeMatchTree:
    name: str
    expansion: List[TerminalDef]

    def __init__(self, name: str, expansion: List[TerminalDef]):
        ...

    def __call__(self, args: List[Union[str, Tree]]):
        ...


class Reconstructor:

    def __init__(self, parser: Lark, term_subs: Dict[str, str] = ...):
        ...

    def reconstruct(self, tree: Tree) -> str:
        ...
