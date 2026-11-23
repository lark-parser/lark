"""Implement https://www.python.org/dev/peps/pep-0514/ to discover interpreters - Windows only."""

from __future__ import annotations

import logging
import re
import sys
import winreg
from logging import basicConfig, getLogger
from pathlib import Path, PureWindowsPath
from typing import TYPE_CHECKING, Any, Final, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Generator

_LOGGER: Final[logging.Logger] = getLogger(__name__)
_ARCH_RE: Final[re.Pattern[str]] = re.compile(
    r"""
    ^
    (\d+)   # bitness number
    bit     # literal suffix
    $
    """,
    re.VERBOSE,
)
_VERSION_RE: Final[re.Pattern[str]] = re.compile(
    r"""
    ^
    (?P<major>\d+)            # major
    (?:\.(?P<minor>\d+))?     # optional minor
    (?:\.(?P<micro>\d+))?     # optional micro
    $
    """,
    re.VERBOSE,
)
_THREADED_TAG_RE: Final[re.Pattern[str]] = re.compile(
    r"""
    ^
    \d+              # major
    (\.\d+){0,2}     # optional minor/micro
    t                # free-threaded flag
    $
    """,
    re.VERBOSE | re.IGNORECASE,
)


def _enum_keys(key: Any) -> Generator[str, None, None]:  # ruff:ignore[any-type] Windows-only handle
    at = 0
    while True:
        try:
            yield winreg.EnumKey(key, at)  # ty: ignore[unresolved-attribute] Windows-only
        except OSError:
            break
        at += 1


def _get_value(key: Any, value_name: str | None) -> Any:  # ruff:ignore[any-type] registry value
    try:
        return winreg.QueryValueEx(key, value_name)[0]  # ty: ignore[unresolved-attribute] Windows-only
    except OSError:
        return None


class _RegistrySpec(NamedTuple):
    company: str
    major: int | None
    minor: int | None
    arch: int
    threaded: bool
    exe: str
    args: str | None


def discover_pythons() -> Generator[_RegistrySpec, None, None]:
    for hive, hive_name, key, flags, default_arch in [
        # ty: ignore[unresolved-attribute] winreg constants exist only on Windows
        (winreg.HKEY_CURRENT_USER, "HKEY_CURRENT_USER", r"Software\Python", 0, 64),
        # ty: ignore[unresolved-attribute] winreg constants exist only on Windows
        (winreg.HKEY_LOCAL_MACHINE, "HKEY_LOCAL_MACHINE", r"Software\Python", winreg.KEY_WOW64_64KEY, 64),
        # ty: ignore[unresolved-attribute] winreg constants exist only on Windows
        (winreg.HKEY_LOCAL_MACHINE, "HKEY_LOCAL_MACHINE", r"Software\Python", winreg.KEY_WOW64_32KEY, 32),
    ]:
        yield from _process_set(hive, hive_name, key, flags, default_arch)


def _process_set(
    hive: int,
    hive_name: str,
    key: str,
    flags: int,
    default_arch: int,
) -> Generator[_RegistrySpec, None, None]:
    try:
        # ty: ignore[unresolved-attribute] winreg is Windows-only
        with winreg.OpenKeyEx(hive, key, 0, winreg.KEY_READ | flags) as root_key:
            for company in _enum_keys(root_key):
                if company == "PyLauncher":  # reserved
                    continue
                yield from _process_company(hive_name, company, root_key, default_arch)
    except OSError:
        pass


def _process_company(
    hive_name: str,
    company: str,
    root_key: Any,  # ruff:ignore[any-type] Windows-only handle
    default_arch: int,
) -> Generator[_RegistrySpec, None, None]:
    with winreg.OpenKeyEx(root_key, company) as company_key:  # ty: ignore[unresolved-attribute] Windows-only
        for tag in _enum_keys(company_key):
            if (spec := _process_tag(hive_name, company, company_key, tag, default_arch)) is not None:
                yield spec


# ruff:ignore[any-type] winreg handles have no portable type
def _process_tag(hive_name: str, company: str, company_key: Any, tag: str, default_arch: int) -> _RegistrySpec | None:
    with winreg.OpenKeyEx(company_key, tag) as tag_key:  # ty: ignore[unresolved-attribute] Windows-only
        for candidate, key_path in [
            (_get_value(tag_key, "SysVersion"), f"{hive_name}/{company}/{tag}/SysVersion"),
            (tag, f"{hive_name}/{company}/{tag}"),
        ]:
            if candidate is None:
                continue
            try:
                version = _parse_version(candidate)
            except ValueError as sys_version:
                _msg(key_path, sys_version)
            else:
                break
        else:
            return None
        arch = default_arch
        if (arch_str := _get_value(tag_key, "SysArchitecture")) is not None:
            try:
                arch = _parse_arch(arch_str)
            except ValueError as sys_arch:
                _msg(f"{hive_name}/{company}/{tag}/SysArchitecture", sys_arch)
        if (exe_data := _load_exe(hive_name, company, company_key, tag)) is None:
            return None
        exe, args = exe_data
        display_name = _get_value(tag_key, "DisplayName")
        if display_name is not None and not isinstance(display_name, str):
            _msg(f"{hive_name}/{company}/{tag}/DisplayName", f"display name is not string: {display_name!r}")
        threaded = bool(_THREADED_TAG_RE.match(tag)) or (
            isinstance(display_name, str) and "freethreaded" in display_name.lower()
        )
        return _RegistrySpec(company, version.major, version.minor, arch, threaded, exe, args)


# ruff:ignore[any-type] winreg handles have no portable type
def _load_exe(hive_name: str, company: str, company_key: Any, tag: str) -> tuple[str, str | None] | None:
    key_path = f"{hive_name}/{company}/{tag}"
    try:
        # ty: ignore[unresolved-attribute] winreg is Windows-only
        with winreg.OpenKeyEx(company_key, rf"{tag}\InstallPath") as ip_key, ip_key:
            if (exe := _resolve_exe(ip_key, key_path)) is not None and Path(exe).exists():
                if (args := _get_value(ip_key, "ExecutableArguments")) is None or isinstance(args, str):
                    return exe, args if args and args.strip() else None
                _msg(f"{key_path}/ExecutableArguments", f"expected a string, got {type(args).__name__}")
                return None
            _msg(key_path, f"could not load exe with value {exe}")
    except OSError:
        _msg(f"{key_path}/InstallPath", "missing")
    return None


def _resolve_exe(ip_key: Any, key_path: str) -> str | None:  # ruff:ignore[any-type] Windows-only handle
    if (exe := _get_value(ip_key, "ExecutablePath")) is None:
        if (exe := _get_value(ip_key, None)) is None:
            _msg(key_path, "no ExecutablePath or default for it")
            return None
        if isinstance(exe, str):
            exe = str(PureWindowsPath(exe) / "python.exe")
    if not isinstance(exe, str) or not PureWindowsPath(exe).is_absolute():
        _msg(key_path, f"expected an absolute executable path, got {exe!r}")
        return None
    return exe


def _parse_arch(arch_str: Any) -> int:  # ruff:ignore[any-type] untyped registry value
    if isinstance(arch_str, str):
        if match := _ARCH_RE.match(arch_str):
            return int(next(iter(match.groups())))
        error = f"invalid format {arch_str}"
    else:
        error = f"arch is not string: {arch_str!r}"
    raise ValueError(error)


class _Version(NamedTuple):
    major: int | None
    minor: int | None
    micro: int | None


def _parse_version(version_str: Any) -> _Version:  # ruff:ignore[any-type] untyped registry value
    if isinstance(version_str, str):
        if match := _VERSION_RE.match(version_str):
            major, minor, micro = match["major"], match["minor"], match["micro"]
            return _Version(
                int(major) if major is not None else None,
                int(minor) if minor is not None else None,
                int(micro) if micro is not None else None,
            )
        error = f"invalid format {version_str}"
    else:
        error = f"version is not string: {version_str!r}"
    raise ValueError(error)


def _msg(path: str, what: str | Exception) -> None:
    _LOGGER.warning("PEP-514 violation in Windows Registry at %s error: %s", path, what)


def _run() -> None:
    basicConfig()
    sys.stdout.write("\n".join(sorted([repr(tuple(spec)) for spec in discover_pythons()])))
    sys.stdout.write("\n")


__all__ = [
    "discover_pythons",
]


if __name__ == "__main__":
    _run()
