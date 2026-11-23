from __future__ import annotations

import logging
import os
import re
from types import MappingProxyType
from typing import TYPE_CHECKING, ClassVar, Final

if TYPE_CHECKING:
    from argparse import Action
    from typing import Any

LOGGER: Final[logging.Logger] = logging.getLogger(__name__)  # simplint: ignore[module-variable-prefix]  # existing name
_SPECIFIER_OPERATORS: Final[tuple[str, ...]] = ("===", "==", "!=", "~=", "<=", ">=", "<", ">")
# the first clause of a version specifier may name the implementation, as in "cpython>=3.9"
_SPECIFIER_START: Final[re.Pattern[str]] = re.compile(
    rf"[A-Za-z]*\s*(?:{'|'.join(_SPECIFIER_OPERATORS)})",
)


class TypeData:
    """Converts a raw option value to the type the option expects.

    :param default_type: the type of the option
    :param as_type: the type each item of a list option is converted to

    """

    def __init__(self, default_type: type, as_type: type) -> None:
        self.default_type = default_type
        self.as_type = as_type

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(base={self.default_type}, as={self.as_type})"

    # a converter returns the type of the option it converts
    def convert(self, value: str) -> Any:  # ruff:ignore[any-type]
        """Convert a raw option value to the type of the option.

        :param value: the raw value

        :returns: the converted value

        """
        return self.default_type(value)


class BoolType(TypeData):
    """Converter for boolean options, accepting the usual yes and no spellings.

    :var BOOLEAN_STATES: the accepted spellings, mapped to the boolean they stand for

    """

    BOOLEAN_STATES: ClassVar[dict[str, bool]] = {
        "1": True,
        "yes": True,
        "true": True,
        "on": True,
        "0": False,
        "no": False,
        "false": False,
        "off": False,
    }

    def convert(self, value: str) -> bool:
        """Convert the text to a boolean, ignoring case.

        :param value: the text to convert

        :returns: the boolean value

        :raises ValueError: when the text is not a recognized boolean spelling

        """
        if value.lower() not in self.BOOLEAN_STATES:
            msg = f"Not a boolean: {value}"
            raise ValueError(msg)
        return self.BOOLEAN_STATES[value.lower()]


class NoneType(TypeData):  # simplint: ignore[unexported-public-name]  # existing name
    """Converter for options that may be empty, where an empty value means ``None``."""  # simplint: ignore[function-docstring]  # existing docs

    def convert(self, value: str) -> str | None:
        """Return ``None`` for an empty value, otherwise the value as a string.

        :param value: the raw value

        :returns: the value, ``None`` when empty

        """  # simplint: ignore[function-docstring]  # existing docs
        if not value:
            return None
        return str(value)


class ListType(TypeData):
    """Converter for options that take a list of values."""  # simplint: ignore[function-docstring]  # existing docs

    # flatten is accepted but ignored, removing it would change the converter signature
    def convert(self, value: str | list[str], flatten: bool = True) -> list[Any]:  # ruff:ignore[unused-method-argument, boolean-default-value-positional-argument]  # simplint: ignore[imprecise-annotation]  # runtime option type
        """Convert each item of the list to the type of the option.

        :param value: the raw value, a string or a list of strings
        :param flatten: accepted for the converter signature and ignored

        :returns: the converted items

        """  # simplint: ignore[function-docstring]  # existing docs
        values = self.split_values(value)
        result = []
        for a_value in values:
            result.extend(item for item in a_value.split(os.pathsep) if item)
        return [self.as_type(i) for i in result]

    def split_values(self, value: str | bytes | list[str]) -> list[str]:
        """Split a raw value into its items: by line when it has several lines, otherwise by comma.

        :param value: the raw value

        :returns: the items

        """  # simplint: ignore[function-docstring]  # existing docs
        if isinstance(value, bytes):
            value = value.decode()
        if isinstance(value, str):
            # `splitlines` rather than a manual newline check, so its full line-boundary logic applies.
            values = value.splitlines()
            if len(values) <= 1:
                return self._join_specifiers([stripped for x in value.split(",") if (stripped := x.strip())])
            return [stripped for x in values if (stripped := x.strip())]
        return list(value)

    # a comma also joins the clauses of one version specifier, so ">=3.9,<3.10" is one value; a clause is a piece that
    # starts with a comparison operator and follows a piece that starts a specifier or is a clause itself
    @staticmethod
    def _join_specifiers(items: list[str]) -> list[str]:
        result: list[str] = []
        for item in items:
            if result and item.startswith(_SPECIFIER_OPERATORS) and _SPECIFIER_START.match(result[-1]):
                result[-1] = f"{result[-1]},{item}"
            else:
                result.append(item)
        return result


# the converted value's type depends on as_type
def convert(value: str, as_type: TypeData, source: str) -> Any:  # ruff:ignore[any-type]
    """Convert the value as a given type where the value comes from the given source.

    :param value: the raw value to convert
    :param as_type: the type to convert the value to
    :param source: where the value comes from, used when logging a failed conversion

    :returns: the converted value

    """
    try:
        return as_type.convert(value)
    except Exception as exception:
        LOGGER.warning("%s failed to convert %r as %r because %r", source, value, as_type, exception)
        raise


_CONVERT: Final[MappingProxyType[type, type]] = MappingProxyType({bool: BoolType, type(None): NoneType, list: ListType})


def get_type(action: Action) -> TypeData:
    """Return the converter for the type of an argparse action.

    :param action: the argparse action to convert values for

    :returns: the converter matching the default value of the action

    """
    # a flag that stores a bool over an unset default is tri-state, so its env var and ini values read as bools
    default_type = bool if action.default is None and isinstance(action.const, bool) else type(action.default)
    return _CONVERT.get(default_type, TypeData)(default_type, default_type if action.type is None else action.type)


__all__ = [
    "BoolType",
    "TypeData",
    "convert",
    "get_type",
]
