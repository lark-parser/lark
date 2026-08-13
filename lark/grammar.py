from typing import Any, Dict, Optional, Tuple, ClassVar, Sequence, Callable

from .utils import Serialize

###{standalone
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

    def renamed(self, f: Callable[[str], str]) -> 'Symbol':
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

    def serialize(self, memo: Optional[Dict[Any, Any]] = None) -> Dict[str, Any]:
        # TODO: this is here because self.name can be a Token instance.
        #       remove this function when the issue is fixed. (backwards-incompatible)
        return {'name': str(self.name), '__type__': 'NonTerminal'}


class RuleOptions(Serialize):
    __serialize_fields__ = ('keep_all_tokens', 'expand1', 'priority', 'template_source', 'empty_indices')

    keep_all_tokens: bool
    expand1: bool
    priority: Optional[int]
    template_source: Optional[str]
    empty_indices: Tuple[bool, ...]

    def __init__(
        self,
        keep_all_tokens: bool = False,
        expand1: bool = False,
        priority: Optional[int] = None,
        template_source: Optional[str] = None,
        empty_indices: Tuple[bool, ...] = ()
    ) -> None:
        self.keep_all_tokens = keep_all_tokens
        self.expand1 = expand1
        self.priority = priority
        self.template_source = template_source
        self.empty_indices = empty_indices

    def __repr__(self) -> str:
        return (
            f'RuleOptions({self.keep_all_tokens!r}, {self.expand1!r}, '
            f'{self.priority!r}, {self.template_source!r}, {self.empty_indices!r})'
        )


class Rule(Serialize):
    """
    origin : a symbol
    expansion : a list of symbols
    order : index of this expansion amongst all rules of the same name
    """
    __slots__ = ('origin', 'expansion', 'alias', 'options', 'order', '_hash')

    __serialize_fields__ = ('origin', 'expansion', 'order', 'alias', 'options')
    __serialize_namespace__ = (Terminal, NonTerminal, RuleOptions)

    origin: NonTerminal
    expansion: Sequence[Symbol]
    order: int
    alias: Optional[str]
    options: RuleOptions
    _hash: int

    def __init__(
        self,
        origin: NonTerminal,
        expansion: Sequence[Symbol],
        order: int = 0,
        alias: Optional[str] = None,
        options: Optional[RuleOptions] = None
    ) -> None:
        self.origin = origin
        self.expansion = expansion
        self.alias = alias
        self.order = order
        self.options = options or RuleOptions()
        self._hash = hash((self.origin, tuple(self.expansion)))

    def _deserialize(self) -> None:
        self._hash = hash((self.origin, tuple(self.expansion)))

    def __str__(self) -> str:
        expansion_str = ' '.join(x.name for x in self.expansion)
        return f'<{self.origin.name} : {expansion_str}>'

    def __repr__(self) -> str:
        return f'Rule({self.origin!r}, {self.expansion!r}, {self.alias!r}, {self.options!r})'

    def __hash__(self) -> int:
        return self._hash

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Rule):
            return False
        return self.origin == other.origin and self.expansion == other.expansion
###}
