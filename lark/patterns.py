"""Pattern and Terminal definitions for the Lark lexer.

Contains PatternStr, PatternRE (pattern types) and TerminalDef (terminal definition).
"""

from abc import abstractmethod, ABC
from typing import (
    TypeVar, Type, Dict, Iterator, Collection, Callable, Optional, FrozenSet, Any,
    ClassVar, TYPE_CHECKING, overload
)

from .utils import classify, get_regexp_width, Serialize, logger, TextSlice, TextOrSlice
from .grammar import TOKEN_DEFAULT_PRIORITY


###{standalone
from contextlib import suppress
from copy import copy

try:  # For the standalone parser, we need to make sure that has_interegular is False to avoid NameErrors later on
    has_interegular = False
    import interegular
    has_interegular = bool(interegular)
except NameError:
    has_interegular = False
except ImportError:
    has_interegular = False


class Pattern(Serialize, ABC):
    "An abstraction over regular expressions."

    value: str
    flags: Collection[str]
    raw: Optional[str]
    type: ClassVar[str]

    def __init__(self, value: str, flags: Collection[str] = (), raw: Optional[str] = None) -> None:
        self.value = value
        self.flags = frozenset(flags)
        self.raw = raw

    def __repr__(self):
        return repr(self.to_regexp())

    # Pattern Hashing assumes all subclasses have a different priority!
    def __hash__(self):
        return hash((type(self), self.value, self.flags))

    def __eq__(self, other):
        return type(self) == type(other) and self.value == other.value and self.flags == other.flags

    @abstractmethod
    def to_regexp(self) -> str:
        raise NotImplementedError()

    @property
    @abstractmethod
    def min_width(self) -> int:
        raise NotImplementedError()

    @property
    @abstractmethod
    def max_width(self) -> int:
        raise NotImplementedError()

    def _get_flags(self, value):
        for f in self.flags:
            value = ('(?%s:%s)' % (f, value))
        return value


class PatternStr(Pattern):
    __serialize_fields__ = 'value', 'flags', 'raw'

    type: ClassVar[str] = "str"

    def to_regexp(self) -> str:
        return self._get_flags(re.escape(self.value))

    @property
    def min_width(self) -> int:
        return len(self.value)

    @property
    def max_width(self) -> int:
        return len(self.value)


class PatternRE(Pattern):
    __serialize_fields__ = 'value', 'flags', 'raw', '_width'

    type: ClassVar[str] = "re"

    def to_regexp(self) -> str:
        return self._get_flags(self.value)

    _width = None
    def _get_width(self):
        if self._width is None:
            self._width = get_regexp_width(self.to_regexp())
        return self._width

    @property
    def min_width(self) -> int:
        return self._get_width()[0]

    @property
    def max_width(self) -> int:
        return self._get_width()[1]


class TerminalDef(Serialize):
    "A definition of a terminal"
    __serialize_fields__ = 'name', 'pattern', 'priority'
    __serialize_namespace__ = PatternStr, PatternRE

    name: str
    pattern: Pattern
    priority: int

    def __init__(self, name: str, pattern: Pattern, priority: int = TOKEN_DEFAULT_PRIORITY) -> None:
        assert isinstance(pattern, Pattern), pattern
        self.name = name
        self.pattern = pattern
        self.priority = priority

    def __repr__(self):
        return '%s(%r, %r)' % (type(self).__name__, self.name, self.pattern)

    def user_repr(self) -> str:
        if self.name.startswith('__'):  # We represent a generated terminal
            return self.pattern.raw or self.name
        else:
            return self.name


# We need to import re here for PatternStr.to_regexp
import re

###}
