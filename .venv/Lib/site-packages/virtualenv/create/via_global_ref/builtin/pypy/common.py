from __future__ import annotations  # simplint: ignore[catch-all-module]  # imported by path across the pypy modules

__lazy_modules__ = [
    "pathlib",
    "virtualenv.create.via_global_ref.builtin.ref",
]

import abc
from pathlib import Path
from typing import TYPE_CHECKING

from virtualenv.create.via_global_ref.builtin.ref import PathRefToDest, RefMust, RefWhen
from virtualenv.create.via_global_ref.builtin.via_global_self_do import ViaGlobalRefVirtualenvBuiltin

if TYPE_CHECKING:
    from collections.abc import Generator, Iterator

    from python_discovery import PythonInfo

    from virtualenv.create.via_global_ref.builtin.ref import PathRef


class PyPy(ViaGlobalRefVirtualenvBuiltin, abc.ABC):
    """Base for the built-in creators of PyPy interpreters."""

    @classmethod
    def can_describe(cls, interpreter: PythonInfo) -> bool:
        """Accept PyPy interpreters that the base describer also accepts.

        :param interpreter: the host interpreter to check

        :returns: ``True`` if this creator can describe the interpreter

        """
        return interpreter.implementation == "PyPy" and super().can_describe(interpreter)

    @classmethod
    def _executables(cls, interpreter: PythonInfo) -> Generator[tuple[Path, list[str], str, str]]:
        host = Path(interpreter.system_exe)
        yield host, sorted(f"{name}{PyPy.suffix}" for name in cls.exe_names(interpreter)), RefMust.NA, RefWhen.ANY

    @classmethod
    def exe_names(cls, interpreter: PythonInfo) -> set[str]:
        """The executable names of PyPy environments, the stem and the ``python`` variants.

        :param interpreter: the host interpreter

        :returns: the executable names without suffix

        """
        return {
            cls.exe_stem(),
            "python",
            f"python{interpreter.version_info.major}",
            f"python{interpreter.version_info.major}.{interpreter.version_info.minor}",
        }

    @classmethod
    # yields PathRef, which the base's Generator[ExePathRefToDest] does not allow
    def sources(cls, interpreter: PythonInfo) -> Generator[PathRef]:  # ty: ignore[incompatible-method-override]
        """Yield the executables and the shared libraries of the interpreter.

        :param interpreter: the host interpreter to take the files from

        :yields: the references to the host files

        """
        yield from cls.executables(interpreter)
        for host in cls._add_shared_libs(interpreter):
            yield PathRefToDest(host, dest=lambda self, source: self.bin_dir / source.name)

    @classmethod
    def executables(cls, interpreter: PythonInfo) -> Generator[PathRef]:
        """Yield the host executable as a reference into the environment's bin folder.

        :param interpreter: the host interpreter to take the files from

        :yields: the executable references

        """
        yield from super().sources(interpreter)

    @classmethod
    def _add_shared_libs(cls, interpreter: PythonInfo) -> Generator[Path]:
        # the executable loads a separate libpypy-c next to it: https://github.com/pypy/pypy/issues/1922
        yield from cls._shared_libs(Path(interpreter.system_exe).resolve().parent)

    @classmethod
    def _shared_libs(cls, python_dir: Path) -> Iterator[Path]:
        raise NotImplementedError


__all__ = [
    "PyPy",
]
