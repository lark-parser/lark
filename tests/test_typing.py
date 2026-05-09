"""Static type checks for Lark's generic parse() return type.

This file is never executed — it is checked by mypy only.
Wrong type annotations here will cause a mypy error.
"""
from typing import Iterable, Tuple

from lark import Lark, Token, ParseTree, Transformer
from lark.parser_frontends import ScanMatch


class _ToInt(Transformer[Token, int]):
    def start(self, children): ...

class _Untyped(Transformer):
    def start(self, children): ...


# __init__ without transformer -> Lark[ParseTree]
_p1: Lark[ParseTree] = Lark(r'start: /\d+/')
_r1: ParseTree = _p1.parse("42")

# __init__ with transformer -> Lark[int]
_p2: Lark[int] = Lark(r'start: /\d+/', parser='lalr', transformer=_ToInt())
_r2: int = _p2.parse("42")

# open() without transformer -> Lark[ParseTree]
_p3: Lark[ParseTree] = Lark.open('grammar.lark')
_r3: ParseTree = _p3.parse("42")

# open() with transformer -> Lark[int]
_p4: Lark[int] = Lark.open('grammar.lark', parser='lalr', transformer=_ToInt())
_r4: int = _p4.parse("42")

# open_from_package() without transformer -> Lark[ParseTree]
_p5: Lark[ParseTree] = Lark.open_from_package(__name__, 'grammar.lark')
_r5: ParseTree = _p5.parse("42")

# open_from_package() with transformer -> Lark[int]
_p6: Lark[int] = Lark.open_from_package(__name__, 'grammar.lark', parser='lalr', transformer=_ToInt())
_r6: int = _p6.parse("42")

# untyped transformer
_p7: Lark[int] = Lark(r'start: /\d+/', parser='lalr', transformer=_Untyped())


# scan() preserves the generic type:
# Lark[T].scan(...) -> Iterable[ScanMatch[T]]
_s1: Iterable[ScanMatch[ParseTree]] = _p1.scan("42")
_s2: Iterable[ScanMatch[int]]       = _p2.scan("42")

# Iterating yields ScanMatch[T] whose .range is (int, int) and .value is T
for _m1 in _p1.scan("42"):
    _m1_range: Tuple[int, int] = _m1.range
    _m1_value: ParseTree       = _m1.value

for _m2 in _p2.scan("42"):
    _m2_range: Tuple[int, int] = _m2.range
    _m2_value: int             = _m2.value
