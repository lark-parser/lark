from __future__ import annotations  # simplint: ignore[catch-all-module]  # imported by path across the cpython modules

__lazy_modules__ = [
    "collections",
    "pathlib",
    "virtualenv.create.via_global_ref.builtin.ref",
]

import re
from abc import ABC
from collections import OrderedDict
from pathlib import Path
from typing import TYPE_CHECKING, Final

from virtualenv.create.describe import PosixSupports, WindowsSupports
from virtualenv.create.via_global_ref.builtin.ref import RefMust, RefWhen
from virtualenv.create.via_global_ref.builtin.via_global_self_do import ViaGlobalRefVirtualenvBuiltin

if TYPE_CHECKING:
    from collections.abc import Generator

    from python_discovery import PythonInfo


class CPython(ViaGlobalRefVirtualenvBuiltin, ABC):
    """Base for the built-in creators of CPython interpreters."""

    @classmethod
    def can_describe(cls, interpreter: PythonInfo) -> bool:
        """Accept CPython interpreters that the base describer also accepts.

        :param interpreter: the host interpreter to check

        :returns: ``True`` if this creator can describe the interpreter

        """
        return interpreter.implementation == "CPython" and super().can_describe(interpreter)

    @classmethod
    def exe_stem(cls) -> str:
        """The executable name of CPython environments, ``python``.

        :returns: the executable stem

        """
        return "python"


class CPythonPosix(CPython, PosixSupports, ABC):
    """Create a CPython virtual environment on POSIX platforms."""

    @classmethod
    def _executables(cls, interpreter: PythonInfo) -> Generator[tuple[Path, list[str], str, str]]:
        host_exe = Path(interpreter.system_exe)
        minor = interpreter.version_info.minor
        names = [
            "python",
            "python3",
            f"python3.{minor}",
            *((f"python3.{minor}t",) if interpreter.free_threaded else ()),
            host_exe.name,
        ]
        yield host_exe, list(OrderedDict((i, None) for i in names).keys()), RefMust.NA, RefWhen.ANY


class CPythonWindows(CPython, WindowsSupports, ABC):
    """Base for the built-in creators of CPython interpreters on Windows."""

    @classmethod
    def _executables(cls, interpreter: PythonInfo) -> Generator[tuple[Path, list[str], str, str]]:
        # symlink of the python executables does not work reliably, copy always instead
        # - https://bugs.python.org/issue42013
        # - venv
        host = cls.host_python(interpreter)
        minor = interpreter.version_info.minor
        names = {
            "python.exe",
            "python3.exe",
            "python3",
            # host is the venvlauncher shim on CPython 3.13+, so the alias comes from the interpreter, not from host
            Path(interpreter.system_exe).name,
            *((f"python3.{minor}t.exe",) if interpreter.free_threaded else ()),
        }
        for path in (host.parent / n for n in names):
            yield host, [path.name], RefMust.COPY, RefWhen.ANY
        # for more info on pythonw.exe see https://stackoverflow.com/a/30313091
        python_w = host.parent / "pythonw.exe"
        yield (
            python_w,
            [python_w.name, "pythonw3.exe", *((f"pythonw3.{minor}t.exe",) if interpreter.free_threaded else ())],
            RefMust.COPY,
            RefWhen.ANY,
        )

    @classmethod
    def host_python(cls, interpreter: PythonInfo) -> Path:
        """The interpreter executable that the environment's files come from.

        :param interpreter: the host interpreter

        :returns: the path of the system executable

        """
        return Path(interpreter.system_exe)


def is_mac_os_framework(interpreter: PythonInfo) -> bool:
    """Whether the interpreter is a macOS framework build.

    :param interpreter: the host interpreter to check

    :returns: ``True`` for a framework build of Python 3

    """
    if interpreter.platform == "darwin":
        return interpreter.sysconfig_vars.get("PYTHONFRAMEWORK") == "Python3"
    return False


def is_macos_brew(interpreter: PythonInfo) -> bool:
    """Whether the interpreter is installed by Homebrew.

    :param interpreter: the host interpreter to check

    :returns: ``True`` when the system prefix matches the Homebrew framework layout

    """
    return interpreter.platform == "darwin" and _BREW.fullmatch(interpreter.system_prefix) is not None


_BREW: Final[re.Pattern[str]] = re.compile(
    r"""
    /(?P<prefix>usr/local|opt/homebrew)                # Intel or Apple Silicon Homebrew prefix
    /(?P<formula>opt/python@3\.\d{1,2}|Cellar/python@3\.\d{1,2}/3\.\d{1,2}\.\d{1,2})  # the install layout of python
    /Frameworks/Python\.framework/Versions/3\.\d{1,2}  # the framework that holds the interpreter
    """,
    re.VERBOSE,
)

__all__ = [
    "CPython",
    "CPythonPosix",
    "CPythonWindows",
    "is_mac_os_framework",
    "is_macos_brew",
]
