"""Version specifier support using only standard library (PEP 440 compatible)."""

from __future__ import annotations

import contextlib
import operator
import re
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

DC_KW: Final[dict[str, bool]] = (
    {"frozen": True, "kw_only": True, "slots": True} if sys.version_info >= (3, 10) else {"frozen": True}
)

if TYPE_CHECKING:
    from collections.abc import Iterator

_VERSION_RE: Final[re.Pattern[str]] = re.compile(
    r"""
    ^
    (?P<major>\d+)               # major
    (?:\.(?P<minor>\d+))?        # optional minor
    (?:\.(?P<micro>\d+))?        # optional micro
    (?:(?P<pre_type>a|b|rc)(?P<pre_num>\d+))?  # optional pre-release suffix
    $
    """,
    re.VERBOSE,
)
_SPECIFIER_RE: Final[re.Pattern[str]] = re.compile(
    r"""
    ^
    (?P<op>===|==|~=|!=|<=|>=|<|>)  # operator
    \s*
    (?P<version>.+)                       # version string
    $
    """,
    re.VERBOSE,
)


@dataclass(**DC_KW)
class SimpleSpecifierSet:
    """
    Simple PEP 440-like specifier set using only standard library.

    :param specifiers_str: the original comma-separated specifier string.
    :param specifiers: the parsed individual specifiers.
    """

    specifiers_str: str
    specifiers: tuple[SimpleSpecifier, ...]

    @classmethod
    def from_string(cls, specifiers_str: str = "") -> SimpleSpecifierSet:
        """
        Parse a comma-separated PEP 440 specifier string (e.g. ``>=3.10,<4``).

        :param specifiers_str: the specifier string to parse.
        :returns: the parsed specifier set.
        """
        stripped = specifiers_str.strip()
        specs: list[SimpleSpecifier] = []
        if stripped:
            for spec_item in stripped.split(","):
                if item := spec_item.strip():
                    with contextlib.suppress(ValueError):
                        specs.append(SimpleSpecifier.from_string(item))
        return cls(specifiers_str=stripped, specifiers=tuple(specs))

    def __iter__(self) -> Iterator[SimpleSpecifier]:
        return iter(self.specifiers)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SimpleSpecifierSet):
            return NotImplemented
        return self.specifiers_str == other.specifiers_str

    def __hash__(self) -> int:
        return hash(self.specifiers_str)

    def __str__(self) -> str:
        return self.specifiers_str

    def __repr__(self) -> str:
        return f"SimpleSpecifierSet('{self.specifiers_str}')"

    def contains(self, version_str: str) -> bool:
        """
        Check if a version satisfies all specifiers in the set.

        :param version_str: the version string to test.
        :returns: ``True`` if *version_str* satisfies every specifier.
        """
        if not self.specifiers:
            return True
        return all(spec.contains(version_str) for spec in self.specifiers)


@dataclass(**DC_KW)
class SimpleSpecifier:
    """
    Simple PEP 440-like version specifier using only standard library.

    :param spec_str: the original specifier string (e.g. ``>=3.10``).
    :param operator: the comparison operator (``==``, ``>=``, ``<``, etc.).
    :param version_str: the version portion of the specifier, without the operator.
    :param is_wildcard: ``True`` if the specifier uses a wildcard suffix (``.*``).
    :param wildcard_precision: number of version components before the wildcard, or ``None``.
    :param version: the parsed version, or ``None`` if parsing failed.
    """

    spec_str: str
    operator: str
    version_str: str
    is_wildcard: bool
    wildcard_precision: int | None
    version: SimpleVersion | None

    @classmethod
    def from_string(cls, spec_str: str) -> SimpleSpecifier:
        """
        Parse a single PEP 440 specifier (e.g. ``>=3.10``).

        :param spec_str: the specifier string to parse.
        :returns: the parsed specifier.
        :raises ValueError: if *spec_str* is not a valid specifier.
        """
        stripped = spec_str.strip()
        if not (match := _SPECIFIER_RE.match(stripped)):
            msg = f"Invalid specifier: {spec_str}"
            raise ValueError(msg)
        op = match["op"]
        version_str = match["version"].strip()
        is_wildcard = version_str.endswith(".*")
        wildcard_precision: int | None = None
        if is_wildcard:
            version_str = version_str[:-2]
            wildcard_precision = len(version_str.split("."))
        try:
            version = SimpleVersion.from_string(version_str)
        except ValueError:
            version = None
        return cls(
            spec_str=stripped,
            operator=op,
            version_str=version_str,
            is_wildcard=is_wildcard,
            wildcard_precision=wildcard_precision,
            version=version,
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SimpleSpecifier):
            return NotImplemented
        return self.spec_str == other.spec_str

    def __hash__(self) -> int:
        return hash(self.spec_str)

    def __str__(self) -> str:
        return self.spec_str

    def __repr__(self) -> str:
        return f"SimpleSpecifier('{self.spec_str}')"

    def contains(self, version_str: str) -> bool:
        """
        Check if a version string satisfies this specifier.

        :param version_str: the version string to test.
        :returns: ``True`` if *version_str* satisfies this specifier.
        """
        try:
            candidate = SimpleVersion.from_string(version_str) if isinstance(version_str, str) else version_str
        except ValueError:
            return False
        if (version := self.version) is None:
            return False
        if self.is_wildcard:
            return self._check_wildcard(candidate, version)
        return self._check_standard(candidate, version)

    def _check_wildcard(self, candidate: SimpleVersion, version: SimpleVersion) -> bool:
        if self.operator == "==":
            return candidate.release[: self.wildcard_precision] == version.release[: self.wildcard_precision]
        if self.operator == "!=":
            return candidate.release[: self.wildcard_precision] != version.release[: self.wildcard_precision]
        return False

    def _check_standard(self, candidate: SimpleVersion, version: SimpleVersion) -> bool:
        if self.operator == "===":
            return str(candidate) == str(version)
        if self.operator == "~=":
            return self._check_compatible_release(candidate, version)
        # PEP 440 excludes prereleases of a final release named by an exclusive upper bound.
        if (
            self.operator == "<"
            and candidate.pre_type is not None
            and version.pre_type is None
            and candidate.release == version.release
        ):
            return False
        cmp_ops = {
            "==": operator.eq,
            "!=": operator.ne,
            "<": operator.lt,
            "<=": operator.le,
            ">": operator.gt,
            ">=": operator.ge,
        }
        if self.operator in cmp_ops:
            return cmp_ops[self.operator](candidate, version)
        return False

    def _check_compatible_release(self, candidate: SimpleVersion, version: SimpleVersion) -> bool:
        if candidate < version:
            return False
        # ~=X.Y is >=X.Y, ==X.*: compare all but the last part the spec wrote (release is padded to three).
        # A bare ~=X still compares its one part, so it stays ==X.*.
        prefix = max(self.version_str.count("."), 1)
        return candidate.release[:prefix] == version.release[:prefix]


@dataclass(**DC_KW)
class SimpleVersion:
    """
    Simple PEP 440-like version parser using only standard library.

    :param version_str: the original version string.
    :param major: major version number.
    :param minor: minor version number.
    :param micro: micro (patch) version number.
    :param pre_type: pre-release label (``"a"``, ``"b"``, or ``"rc"``), or ``None``.
    :param pre_num: pre-release sequence number, or ``None``.
    :param release: the ``(major, minor, micro)`` tuple.
    """

    version_str: str
    major: int
    minor: int
    micro: int
    pre_type: str | None
    pre_num: int | None
    release: tuple[int, int, int]

    @classmethod
    def from_string(cls, version_str: str) -> SimpleVersion:
        """
        Parse a PEP 440 version string (e.g. ``3.12.1``).

        :param version_str: the version string to parse.
        :returns: the parsed version.
        :raises ValueError: if *version_str* is not a valid version.
        """
        stripped = version_str.strip()
        if not (match := _VERSION_RE.match(stripped)):
            msg = f"Invalid version: {version_str}"
            raise ValueError(msg)
        major = int(match["major"])
        minor = int(match["minor"]) if match["minor"] else 0
        micro = int(match["micro"]) if match["micro"] else 0
        return cls(
            version_str=stripped,
            major=major,
            minor=minor,
            micro=micro,
            pre_type=match["pre_type"],
            pre_num=int(match["pre_num"]) if match["pre_num"] else None,
            release=(major, minor, micro),
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SimpleVersion):
            return NotImplemented
        return self.release == other.release and self.pre_type == other.pre_type and self.pre_num == other.pre_num

    def __hash__(self) -> int:
        return hash((self.release, self.pre_type, self.pre_num))

    def __lt__(self, other: object) -> bool:  # ruff:ignore[too-many-return-statements] distinct outcomes
        if not isinstance(other, SimpleVersion):
            return NotImplemented
        if self.release != other.release:
            return self.release < other.release
        if self.pre_type is None and other.pre_type is None:
            return False
        if self.pre_type is None:
            return False
        if other.pre_type is None:
            return True
        pre_order: dict[str, int] = {"a": 1, "b": 2, "rc": 3}
        if pre_order[self.pre_type] != pre_order[other.pre_type]:
            return pre_order[self.pre_type] < pre_order[other.pre_type]
        return (self.pre_num or 0) < (other.pre_num or 0)

    def __le__(self, other: object) -> bool:
        return self == other or self < other

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, SimpleVersion):
            return NotImplemented
        return not self <= other

    def __ge__(self, other: object) -> bool:
        return not self < other

    def __str__(self) -> str:
        return self.version_str

    def __repr__(self) -> str:
        return f"SimpleVersion('{self.version_str}')"


__all__ = [
    "DC_KW",
    "SimpleSpecifier",
    "SimpleSpecifierSet",
    "SimpleVersion",
]
