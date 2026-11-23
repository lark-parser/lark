"""Wheel parsing and version selection."""  # simplint: ignore[catch-all-module]  # public import path

from __future__ import annotations

__lazy_modules__ = [
    "email.parser",
    "hashlib",
    "operator",
    "packaging.specifiers",
    "packaging.version",
    "zipfile",
]

import hashlib
import logging
from email.parser import HeaderParser
from operator import attrgetter
from typing import TYPE_CHECKING, Final
from zipfile import ZipFile

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion
from packaging.version import Version as PackagingVersion

if TYPE_CHECKING:
    from pathlib import Path

_LOGGER: Final[logging.Logger] = logging.getLogger(__name__)


def discover_wheels(from_folder: Path, distribution: str, version: str | None, for_py_version: str) -> list[Wheel]:
    """Return the wheels of a distribution in a folder that match the version and Python version, newest first.

    :param from_folder: the folder to search
    :param distribution: the distribution name
    :param version: the version to match, ``None`` for any version
    :param for_py_version: the Python version the wheel must support

    :returns: the matching wheels, sorted by version, newest first

    """
    return sorted(
        (
            wheel
            for filename in from_folder.iterdir()
            if (wheel := Wheel.from_path(filename))
            and wheel.distribution == distribution
            and (version is None or wheel.has_version(version))
            and wheel.support_py(for_py_version)
        ),
        key=attrgetter("parsed_version", "distribution"),
        reverse=True,
    )


class Wheel:
    """Wheel file of a distribution, parsed from its file name.

    :param path: the path to the wheel file
    :param cache_name: the relative path recorded for a downloaded wheel

    :var path: the path to the wheel file

    """

    def __init__(self, path: Path, *, cache_name: str | None = None) -> None:
        self.path = path
        self.cache_name = cache_name or path.name
        self._parts = path.stem.split("-")

    @classmethod
    def from_path(cls, path: Path) -> Wheel | None:
        """Parse a wheel from a path, when the file name has the parts of a wheel name.

        :param path: the path of the file

        :returns: the wheel, ``None`` when the path is not a wheel name

        """
        # https://packaging.python.org/en/latest/specifications/binary-distribution-format/#file-name-convention
        # {distribution}-{version}(-{build tag})?-{python tag}-{abi tag}-{platform tag}.whl
        min_parts: Final[int] = 5
        if path.suffix == ".whl" and len(path.stem.split("-")) >= min_parts:
            return cls(path)
        return None

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.path})"

    def __str__(self) -> str:
        return str(self.path)

    @property
    def sha256(self) -> str:
        """The digest of the wheel contents on disk."""
        digest = hashlib.sha256()
        with self.path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1 << 20), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @property
    def version_tuple(self) -> tuple[int, ...]:
        """The release version of the wheel as a tuple of integers."""
        return self.as_version_tuple(self.version)

    @staticmethod
    def as_version_tuple(version: str) -> tuple[int, ...]:
        """Parse a version into a release tuple.

        :param version: the version to parse

        :returns: the release tuple

        """
        return PackagingVersion(version).release

    @property
    def version(self) -> str:
        """The version part of the wheel file name."""
        return self._parts[1]

    @property
    def name(self) -> str:
        """The file name of the wheel."""
        return self.path.name

    def support_py(self, py_version: str) -> bool:
        """Check whether ``Requires-Python`` admits ``py_version``, a ``major.minor`` string.

        :param py_version: the Python version to check, as ``major.minor``

        :returns: ``True`` when the wheel admits the version or declares no requirement, ``False`` otherwise

        """
        name = f"{self.distribution}-{self.version}.dist-info/METADATA"
        with ZipFile(str(self.path), "r") as zip_file:
            requires = HeaderParser().parsestr(zip_file.read(name).decode("utf-8")).get("Requires-Python")
        if requires is None:
            return True
        try:
            return SpecifierSet(requires).contains(py_version)
        except InvalidSpecifier:
            # skip the wheel as pip does, rather than abort seeding or override the verified embedded wheel
            _LOGGER.warning("skip %s, its Requires-Python %r is not a valid specifier", self.path, requires)
            return False

    @property
    def distribution(self) -> str:
        """The distribution name part of the wheel file name."""
        return self._parts[0]

    def has_version(self, version: str) -> bool:
        """Match equivalent version spellings when selecting a wheel.

        :param version: requested PEP 440 version

        :returns: whether both versions parse and compare equal

        """
        try:
            return self.parsed_version == PackagingVersion(version)
        except InvalidVersion:
            return False

    @property
    def parsed_version(self) -> PackagingVersion:
        """The wheel version as a packaging version, which compares by version order."""
        return PackagingVersion(self.version)


class Version:
    """Version markers and helpers, where the special values stand for the bundled wheel or no version.

    :var bundle: the version marker for the wheel bundled with virtualenv
    :var embed: the version marker for the embedded wheel

    """

    #: the version bundled with virtualenv
    bundle: Final[str] = "bundle"
    embed: Final[str] = "embed"
    #: custom version handlers
    non_version: Final[tuple[str, str]] = (bundle, embed)

    @staticmethod
    def as_pip_req(distribution: str, version: str | None) -> str:
        """Return a requirement string for a distribution at an optional version.

        :param distribution: the distribution name
        :param version: the version, ``None`` for any version

        :returns: the requirement string

        """
        return f"{distribution}{Version.as_version_spec(version)}"

    @staticmethod
    def as_version_spec(version: str | None) -> str:
        """Return the version specifier for a version, empty when there is none.

        :param version: the version, ``None`` for any version

        :returns: the ``==`` specifier, or an empty string

        """
        return "" if (of_version := Version.of_version(version)) is None else f"=={of_version}"

    @staticmethod
    def of_version(value: str | None) -> str | None:
        """Return the normalized version for a value that names a version, ``None`` for the non-version words.

        :param value: the version text, ``None`` for no version

        :returns: the validated version, ``None`` when the value is not a version

        """
        return None if value is None or value in Version.non_version else Version.validate(value)

    @staticmethod
    def validate(value: str) -> str:
        """Normalize seed options before wheel selection or download.

        :param value: version or seed keyword, possibly surrounded by whitespace

        :returns: normalized version or stripped keyword

        :raises ValueError: if the value is invalid or resembles an archive filename

        """
        if (keyword := value.strip()) in {*Version.non_version, "none"}:
            return keyword
        try:
            parsed: Final[PackagingVersion] = PackagingVersion(value)
        except InvalidVersion as exception:
            msg = f"invalid seed version: {value!r}"
            raise ValueError(msg) from exception
        if keyword.lower().endswith((
            ".zip",
            ".whl",
            ".tar",
            ".tar.gz",
            ".tgz",
            ".tar.bz2",
            ".tbz",
            ".tar.xz",
            ".txz",
            ".tlz",
            ".tar.lz",
            ".tar.lzma",
        )):
            msg = f"archive-like seed version: {value!r}"
            raise ValueError(msg)
        return str(parsed)


__all__ = [
    "Version",
    "Wheel",
    "discover_wheels",
]
