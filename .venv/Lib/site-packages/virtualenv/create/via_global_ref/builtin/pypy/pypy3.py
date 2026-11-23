from __future__ import annotations

__lazy_modules__ = [
    "pathlib",
    "virtualenv.create.via_global_ref.builtin.ref",
]

import abc
from pathlib import Path
from typing import TYPE_CHECKING

from virtualenv.create.describe import PosixSupports, Python3Supports, WindowsSupports
from virtualenv.create.via_global_ref.builtin.ref import PathRefToDest

from .common import PyPy

if TYPE_CHECKING:
    from collections.abc import Generator, Iterator

    from python_discovery import PythonInfo

    from virtualenv.create.via_global_ref.builtin.ref import PathRef


class PyPy3(PyPy, Python3Supports, abc.ABC):
    """PyPy 3 interpreters, which are created with the ``pypy3`` executable name."""

    @classmethod
    def exe_stem(cls) -> str:
        """The executable name of PyPy 3 environments, ``pypy3``.

        :returns: the executable stem

        """
        return "pypy3"

    @classmethod
    def exe_names(cls, interpreter: PythonInfo) -> set[str]:
        """The executable names of PyPy 3 environments, adding ``pypy`` to the base names.

        :param interpreter: the host interpreter

        :returns: the executable names without suffix

        """
        return super().exe_names(interpreter) | {"pypy"}


class PyPy3Posix(PyPy3, PosixSupports):
    """PyPy 3 on POSIX."""

    @classmethod
    def _shared_libs(cls, python_dir: Path) -> Iterator[Path]:
        # glob for libpypy3-c.so, libpypy3-c.dylib, libpypy3.9-c.so ...
        return python_dir.glob("libpypy3*.*")

    @classmethod
    def sources(cls, interpreter: PythonInfo) -> Generator[PathRef]:
        """Yield the POSIX executables and, for portable builds, the files under the interpreter's ``lib`` folder.

        :param interpreter: the host interpreter to take the files from

        :yields: the references to the host files

        """
        yield from super().sources(interpreter)
        # PyPy >= 3.8 supports a standard prefix installation, where older versions always used a portable/development
        # style installation. If this is a standard prefix installation, skip the below:
        if interpreter.system_prefix == "/usr":
            return
        yield from cls._portable_lib_sources(interpreter)

    @classmethod
    def _portable_lib_sources(cls, interpreter: PythonInfo) -> Generator[PathRef]:
        # Also copy/symlink anything under prefix/lib, which, for "portable" PyPy builds, includes the tk,tcl runtime
        # and a number of shared objects. In distro-specific builds or on conda this should be empty (on PyPy3.8+ it
        # will, like on CPython, hold the stdlib).
        host_lib = Path(interpreter.system_prefix) / "lib"
        stdlib = Path(interpreter.system_stdlib)
        if host_lib.exists() and host_lib.is_dir():
            if (deps_file := host_lib / "PYPY_PORTABLE_DEPS.txt").exists():
                for line in deps_file.read_text(encoding="utf-8").splitlines():
                    if (dep := line.strip()) and (path := host_lib / dep).exists():
                        yield PathRefToDest(path, dest=cls.to_lib)
            else:
                for path in host_lib.iterdir():
                    if stdlib == path:
                        continue
                    yield PathRefToDest(path, dest=cls.to_lib)

    def to_lib(self, src: Path) -> Path:
        """Map a host file under the ``lib`` folder to its location in the environment.

        :param src: the host file

        :returns: the path of the file inside the environment's ``lib`` folder

        """
        return self.dest / "lib" / src.name


class Pypy3Windows(PyPy3, WindowsSupports):
    """PyPy 3 on Windows."""

    @classmethod
    def _shared_libs(cls, python_dir: Path) -> Iterator[Path]:
        # PyPy does not use a PEP 397 launcher, so all DLLs from the interpreter directory are needed for the venv
        yield from python_dir.glob("*.dll")


__all__ = [
    "PyPy3",
    "PyPy3Posix",
    "Pypy3Windows",
]
