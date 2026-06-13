"""Serialization framework for Lark.

Provides the Serialize base class, SerializeMemoizer, and Enumerator
for safe serialization/deserialization without relying on Pickle.
"""

from typing import Type, TypeVar, List, Dict, Any, Optional

_T = TypeVar("_T", bound="Serialize")


def _deserialize(data: Any, namespace: Dict[str, Any], memo: Dict) -> Any:
    if isinstance(data, dict):
        if '__type__' in data:  # Object
            class_ = namespace[data['__type__']]
            return class_.deserialize(data, memo)
        elif '@' in data:
            return memo[data['@']]
        return {key:_deserialize(value, namespace, memo) for key, value in data.items()}
    elif isinstance(data, list):
        return [_deserialize(value, namespace, memo) for value in data]
    return data


def _serialize(value: Any, memo: Optional["SerializeMemoizer"]) -> Any:
    if isinstance(value, Serialize):
        return value.serialize(memo)
    elif isinstance(value, list):
        return [_serialize(elem, memo) for elem in value]
    elif isinstance(value, frozenset):
        return list(value)  # TODO reversible?
    elif isinstance(value, dict):
        return {key:_serialize(elem, memo) for key, elem in value.items()}
    # assert value is None or isinstance(value, (int, float, str, tuple)), value
    return value


class Serialize:
    """Safe-ish serialization interface that doesn't rely on Pickle

    Attributes:
        __serialize_fields__ (List[str]): Fields (aka attributes) to serialize.
        __serialize_namespace__ (list): List of classes that deserialization is allowed to instantiate.
                                        Should include all field types that aren't builtin types.
    """

    def memo_serialize(self, types_to_memoize: List) -> Any:
        memo = SerializeMemoizer(types_to_memoize)
        return self.serialize(memo), memo.serialize()

    def serialize(self, memo = None) -> Dict[str, Any]:
        if memo and memo.in_types(self):
            return {'@': memo.memoized.get(self)}

        fields = getattr(self, '__serialize_fields__')
        res = {f: _serialize(getattr(self, f), memo) for f in fields}
        res['__type__'] = type(self).__name__
        if hasattr(self, '_serialize'):
            self._serialize(res, memo)
        return res

    @classmethod
    def deserialize(cls: Type[_T], data: Dict[str, Any], memo: Dict[int, Any]) -> _T:
        namespace = getattr(cls, '__serialize_namespace__', [])
        namespace = {c.__name__:c for c in namespace}

        fields = getattr(cls, '__serialize_fields__')

        if '@' in data:
            return memo[data['@']]

        inst = cls.__new__(cls)
        for f in fields:
            try:
                setattr(inst, f, _deserialize(data[f], namespace, memo))
            except KeyError as e:
                raise KeyError("Cannot find key for class", cls, e)

        if hasattr(inst, '_deserialize'):
            inst._deserialize()

        return inst


class SerializeMemoizer(Serialize):
    "A version of serialize that memoizes objects to reduce space"

    __serialize_fields__ = 'memoized',

    def __init__(self, types_to_memoize: List) -> None:
        self.types_to_memoize = tuple(types_to_memoize)
        self.memoized = Enumerator()

    def in_types(self, value: Serialize) -> bool:
        return isinstance(value, self.types_to_memoize)

    def serialize(self) -> Dict[int, Any]:  # type: ignore[override]
        return _serialize(self.memoized.reversed(), None)

    @classmethod
    def deserialize(cls, data: Dict[int, Any], namespace: Dict[str, Any], memo: Dict[Any, Any]) -> Dict[int, Any]:  # type: ignore[override]
        return _deserialize(data, namespace, memo)


class Enumerator(Serialize):
    def __init__(self) -> None:
        self.enums: Dict[Any, int] = {}

    def get(self, item) -> int:
        if item not in self.enums:
            self.enums[item] = len(self.enums)
        return self.enums[item]

    def __len__(self):
        return len(self.enums)

    def reversed(self) -> Dict[int, Any]:
        r = {v: k for k, v in self.enums.items()}
        assert len(r) == len(self.enums)
        return r
