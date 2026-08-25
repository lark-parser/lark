import sys
from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple, ClassVar, Sequence, Callable

from .utils import Serialize

if TYPE_CHECKING:
    if sys.version_info >= (3, 11):
        from typing import Self
    else:
        from typing_extensions import Self
    from .utils import SerializeMemoizer

TOKEN_DEFAULT_PRIORITY = 0


class Symbol(Serialize):
    __slots__ = ('name',)

    name: str
    is_term: ClassVar[bool] = NotImplemented

    def __init__(self, name: str) -> None:
        self.name = name

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Symbol):
            return NotImplemented
        return self.is_term == other.is_term and self.name == other.name

    def __ne__(self, other: Any) -> bool:
        return not (self == other)

    def __hash__(self) -> int:
        return hash(self.name)

    def __repr__(self) -> str:
        return f'{type(self).__name__}({self.name!r})'

    @property
    def fullrepr(self) -> str:
        return repr(self)

    def renamed(self, f: Callable[[str], str]) -> 'Self':
        return type(self)(f(self.name))


class Terminal(Symbol):
    __serialize_fields__ = ('name', 'filter_out')

    is_term: ClassVar[bool] = True
    filter_out: bool

    def __init__(self, name: str, filter_out: bool = False) -> None:
        super().__init__(name)
        self.filter_out = filter_out

    @property
    def fullrepr(self) -> str:
        return f'{type(self).__name__}({self.name!r}, {self.filter_out!r})'

    def renamed(self, f: Callable[[str], str]) -> 'Terminal':
        return type(self)(f(self.name), self.filter_out)


class NonTerminal(Symbol):
    __serialize_fields__ = ('name',)

    is_term: ClassVar[bool] = False

    def serialize(self, memo: Any = None) -> Dict[str, Any]:
        # TODO this is here because self.name can be a Token instance.
        #      remove this function when the issue is fixed. (backwards-incompatible)
        return {'name': str(self.name), '__type__': 'NonTerminal'}
