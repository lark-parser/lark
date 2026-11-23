# simplint: ignore[flattened-package]  # ruff: ignore[commented-out-code]  # keep the existing private path
"""A Python specification is an abstract requirement definition of an interpreter."""

from __future__ import annotations

import pathlib
import re
from typing import Final, NamedTuple

from ._py_info import normalize_isa
from ._specifier import SimpleSpecifier, SimpleSpecifierSet, SimpleVersion

_MODIFIERS: Final[str] = r"""
    (?P<threaded>t)?                # free-threaded flag
    (?P<debug>d|(?:-dbg|-debug)(?=-|$))?  # debug build flag (d, -dbg or -debug)
    (?:-(?P<arch>32|64))?           # architecture bitness
    (?:-(?P<machine>[a-zA-Z0-9_.]+))?  # ISA (e.g. arm64, x86_64, i86pc.64bit)
    $
"""
_PATTERN: Final[re.Pattern[str]] = re.compile(
    rf"""
    ^
    (?P<impl>[a-zA-Z]+)?            # implementation (e.g. cpython, pypy)
    (?P<version>[0-9.]+)?           # version (e.g. 3.12, 3.12.1)
    {_MODIFIERS}
    """,
    re.VERBOSE,
)
_SPECIFIER_PATTERN: Final[re.Pattern[str]] = re.compile(
    rf"""
    ^
    (?:(?P<impl>[A-Za-z]+)\s*)?     # optional implementation prefix
    (?P<spec>(?:===|==|~=|!=|<=|>=|<|>).*?)  # PEP 440 version specifier, lazy so the modifiers can follow it
    {_MODIFIERS}
    """,
    re.VERBOSE,
)

#: implementation names accepted as a spec prefix
KNOWN_IMPLEMENTATIONS: Final[tuple[str, ...]] = ("python", "cpython", "pypy", "graalpy")

SpecifierSet = SimpleSpecifierSet
Version = SimpleVersion
InvalidSpecifier = ValueError
InvalidVersion = ValueError


class _VersionParts(NamedTuple):
    major: int | None
    minor: int | None
    micro: int | None


def _parse_version_parts(version: str) -> _VersionParts:
    max_version_parts = 3
    single_digit_max = 9
    versions = tuple(int(i) for i in version.split(".") if i)
    if not versions:
        msg = "version must contain a numeric component"
        raise ValueError(msg)
    if len(versions) > max_version_parts:
        msg = "too many version parts"
        raise ValueError(msg)
    if len(versions) == max_version_parts:
        return _VersionParts(versions[0], versions[1], versions[2])
    if len(versions) == 2:  # ruff:ignore[magic-value-comparison] a two-part version is major.minor
        return _VersionParts(versions[0], versions[1], None)
    version_data = versions[0]
    return _VersionParts(
        int(str(version_data)[0]),
        int(str(version_data)[1:]) if version_data > single_digit_max else None,
        None,
    )


def _parse_spec_pattern(string_spec: str) -> PythonSpec | None:
    if not (match := re.match(_PATTERN, string_spec)):
        return None
    release, threaded = (None, None, None), None
    if (version := match["version"]) is not None:
        try:
            release = _parse_version_parts(version)
        except ValueError:
            return None
        threaded = bool(match["threaded"])
    return _spec_from_match(string_spec, match, release, threaded=threaded, version_specifier=None)


def _spec_from_match(
    string_spec: str,
    match: re.Match[str],
    release: tuple[int | None, int | None, int | None],
    *,
    threaded: bool | None,
    version_specifier: SpecifierSet | None,
) -> PythonSpec:
    impl = match["impl"]
    if (alias := None if impl is None else impl.lower()) in {"py", "python"}:
        impl = None
    elif alias == "graalvm":
        impl = "graalpy"
    return PythonSpec(
        string_spec,
        impl,
        *release,
        None if (arch := match["arch"]) is None else int(arch),
        None,
        free_threaded=threaded,
        machine=None if (machine := match["machine"]) is None else normalize_isa(machine),
        debug=True if match["debug"] else None,  # unconstrained unless an explicit d/-dbg/-debug marker is present
        version_specifier=version_specifier,
    )


class PythonSpec:
    """
    Contains specification about a Python Interpreter.

    :param str_spec: the raw specification string as provided by the caller.

    :param implementation: interpreter implementation name (e.g. ``"cpython"``, ``"pypy"``), or ``None`` for any.
    :param major: required major version, or ``None`` for any.
    :param minor: required minor version, or ``None`` for any.
    :param micro: required micro (patch) version, or ``None`` for any.
    :param architecture: required pointer-size bitness (``32`` or ``64``), or ``None`` for any.

    :param path: filesystem path to a specific interpreter, or ``None``.
    :param free_threaded: whether a free-threaded build is required, or ``None`` for any.
    :param machine: required ISA (e.g. ``"arm64"``), or ``None`` for any.
    :param debug: whether a debug (``Py_DEBUG``) build is required, or ``None`` for any.
    :param version_specifier:
        `version specifier <https://packaging.python.org/en/latest/specifications/version-specifiers/>`_
        constraints, or ``None``.
    """

    def __init__(  # ruff:ignore[too-many-arguments, too-many-positional-arguments] positional callers
        self,
        str_spec: str,
        implementation: str | None,
        major: int | None,
        minor: int | None,
        micro: int | None,
        architecture: int | None,
        path: str | None,
        *,
        free_threaded: bool | None = None,
        machine: str | None = None,
        debug: bool | None = None,
        version_specifier: SpecifierSet | None = None,
    ) -> None:
        self.str_spec = str_spec
        self.implementation = implementation
        self.major = major
        self.minor = minor
        self.micro = micro
        self.free_threaded = free_threaded
        self.architecture = architecture
        self.machine = machine
        self.debug = debug
        self.path = path
        self.version_specifier = version_specifier

    @classmethod
    def from_string_spec(cls, string_spec: str) -> PythonSpec:
        """
        Parse a string specification into a :class:`PythonSpec`.

        :param string_spec: an interpreter spec — an absolute path, a version string, an implementation prefix,
            or a `version specifier <https://packaging.python.org/en/latest/specifications/version-specifiers/>`_.
        :returns: the parsed specification.
        :raises ValueError: if the spec starts with a version specifier operator but does not parse as one.
        """
        if pathlib.Path(string_spec).is_absolute():
            return cls(string_spec, None, None, None, None, None, string_spec)
        if result := _parse_spec_pattern(string_spec):
            return result
        if result := _parse_specifier(string_spec):
            return result
        return cls(string_spec, None, None, None, None, None, string_spec)

    def __repr__(self) -> str:
        name = type(self).__name__
        params = (
            "implementation",
            "major",
            "minor",
            "micro",
            "architecture",
            "machine",
            "path",
            "free_threaded",
            "debug",
            "version_specifier",
        )
        return f"{name}({', '.join(f'{k}={getattr(self, k)}' for k in params if getattr(self, k) is not None)})"

    def generate_re(self, *, windows: bool, all_implementations: bool = False) -> re.Pattern:
        """
        Generate a regular expression for matching interpreter filenames.

        :param windows: if ``True``, require a ``.exe`` suffix.
        :param all_implementations: when ``True`` and the spec does not constrain the implementation, match every
            filename in :data:`KNOWN_IMPLEMENTATIONS` instead of only ``python``. A free-threaded or debug build the
            spec leaves open also matches its marked name, such as ``python3.13t`` or ``python3.13-dbg``. Used by
            enumeration APIs.
        :returns: a compiled pattern matching the filenames the spec accepts.
        """
        version = r"{}(\.{}(\.{})?)?".format(
            *(r"\d+" if v is None else v for v in (self.major, self.minor, self.micro)),
        )
        if self.implementation is not None:
            impl = f"python|{re.escape(self.implementation)}"
        elif all_implementations:
            impl = "|".join(re.escape(i) for i in KNOWN_IMPLEMENTATIONS)
        else:
            impl = "python"
        # An unconstrained single lookup must not depend on directory order to choose a variant.
        mod = "t?" if self.free_threaded or (all_implementations and self.free_threaded is None) else ""
        dbg = "(?:d|-dbg|-debug)?" if self.debug or (all_implementations and self.debug is None) else ""
        suffix = r"\.exe" if windows else ""
        version_conditional = "?" if windows or self.major is None else ""
        return re.compile(
            rf"(?P<impl>{impl})(?P<v>{version}{mod}){version_conditional}{dbg}{suffix}$",
            flags=re.IGNORECASE,
        )

    def satisfies(self, spec: PythonSpec) -> bool:  # ruff:ignore[too-many-return-statements] distinct outcomes
        """
        Check if this spec is compatible with the given *spec* (e.g. PEP-514 on Windows).

        :param spec: the requirement to check against.
        :returns: ``True`` if this spec is compatible with *spec*.
        """
        if spec.is_abs and self.is_abs and self.path != spec.path:
            return False
        if (
            spec.implementation is not None
            and self.implementation is not None
            and spec.implementation.lower() != self.implementation.lower()
        ):
            return False
        if spec.architecture is not None and spec.architecture != self.architecture:
            return False
        if spec.machine is not None and self.machine is not None and spec.machine != self.machine:
            return False
        if spec.free_threaded is not None and spec.free_threaded != self.free_threaded:
            return False
        if spec.version_specifier is not None and not self._check_version_specifier(spec):
            return False
        return all(
            req is None or our is None or our == req
            for our, req in zip((self.major, self.minor, self.micro), (spec.major, spec.minor, spec.micro))
        )

    @property
    def is_abs(self) -> bool:
        """``True`` if the spec refers to an absolute filesystem path."""
        return self.path is not None and pathlib.Path(self.path).is_absolute()

    def _check_version_specifier(self, spec: PythonSpec) -> bool:
        # Check if version specifier is satisfied.
        components: list[int] = []
        for part in (self.major, self.minor, self.micro):
            if part is None:
                break
            components.append(part)
        if not components:
            return True

        if spec.version_specifier is None:
            return True
        for item in spec.version_specifier:
            required_precision = self._get_required_precision(item)
            if required_precision is None or len(components) < required_precision:
                continue
            # Registry versions omit prerelease status, so a matching release still needs interrogation.
            if (
                (version := item.version) is not None
                and version.pre_type is not None
                and tuple(components[:required_precision]) == version.release[:required_precision]
            ):
                continue
            # compare at the precision the specifier was written with, as PythonInfo.satisfies does
            if not item.contains(".".join(str(part) for part in components[:required_precision])):
                return False
        return True

    @staticmethod
    def _get_required_precision(item: SimpleSpecifier) -> int | None:
        if item.version is None:
            return None
        if item.wildcard_precision is not None:
            return item.wildcard_precision
        return _GET_REQUIRED_PRECISION_PATTERN.split(item.version_str, maxsplit=1)[0].count(".") + 1


def _parse_specifier(string_spec: str) -> PythonSpec | None:
    if not (match := _SPECIFIER_PATTERN.match(string_spec.strip())):
        return None
    spec_text = match["spec"].strip()
    version_specifier = SpecifierSet.from_string(spec_text)
    # the set never raises: it keeps an unparsable version as None and drops items without an operator
    items = [item for item in spec_text.split(",") if item.strip()]
    if len(items) != len(version_specifier.specifiers) or any(spec.version is None for spec in version_specifier):
        msg = f"invalid version specifier {string_spec!r}"
        raise ValueError(msg)
    return _spec_from_match(
        string_spec,
        match,
        (None, None, None),
        # the version bounds say nothing about the build, so without a trailing t any build qualifies
        threaded=True if match["threaded"] else None,
        version_specifier=version_specifier,
    )


_GET_REQUIRED_PRECISION_PATTERN: Final[re.Pattern[str]] = re.compile(r"a|b|rc")


__all__ = [
    "KNOWN_IMPLEMENTATIONS",
    "PythonSpec",
]
