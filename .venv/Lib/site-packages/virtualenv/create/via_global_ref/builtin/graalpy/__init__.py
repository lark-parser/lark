from __future__ import annotations

__lazy_modules__ = [
    "pathlib",
    "virtualenv.create.via_global_ref.builtin.ref",
]

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

from virtualenv.create.describe import (
    PosixSupports,
    WindowsSupports,
)
from virtualenv.create.via_global_ref.builtin.ref import (
    PathRefToDest,
    RefMust,
    RefWhen,
)
from virtualenv.create.via_global_ref.builtin.via_global_self_do import (
    ViaGlobalRefVirtualenvBuiltin,
)

if TYPE_CHECKING:
    from collections.abc import Generator, Iterator

    from python_discovery import PythonInfo


class GraalPy(ViaGlobalRefVirtualenvBuiltin, ABC):
    """Base for the built-in creators of GraalPy interpreters."""

    @classmethod
    def can_describe(cls, interpreter: PythonInfo) -> bool:
        """Accept GraalPy interpreters that the base describer also accepts.

        :param interpreter: the host interpreter to check

        :returns: ``True`` if this creator can describe the interpreter

        """
        return interpreter.implementation == "GraalPy" and super().can_describe(interpreter)

    @classmethod
    def _executables(cls, interpreter: PythonInfo) -> Generator[tuple[Path, list[str], RefMust, RefWhen], None, None]:
        host = Path(interpreter.system_exe)
        yield host, sorted(f"{name}{cls.suffix}" for name in cls.exe_names(interpreter)), RefMust.NA, RefWhen.ANY

    @classmethod
    def exe_names(cls, interpreter: PythonInfo) -> set[str]:
        """The executable names of GraalPy environments, the stem and the ``python`` variants.

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
    def exe_stem(cls) -> str:
        """The executable name of GraalPy environments, ``graalpy``.

        :returns: the executable stem

        """
        return "graalpy"

    @classmethod
    # yields PathRefToDest, which the base's Generator[ExePathRefToDest] does not allow
    def sources(cls, interpreter: PythonInfo) -> Generator[PathRefToDest]:  # ty: ignore[incompatible-method-override]
        """Yield the host executable, then the native library and JVM folders next to it.

        :param interpreter: the host interpreter to take the files from

        :yields: the references to the host files

        """
        yield from super().sources(interpreter)
        python_dir = Path(interpreter.system_exe).resolve().parent
        if python_dir.name in {"bin", "Scripts"}:
            python_dir = python_dir.parent

        native_lib = cls._native_lib(python_dir / "lib", interpreter.platform)
        if native_lib.exists():
            yield PathRefToDest(native_lib, dest=lambda self, source: self.bin_dir.parent / "lib" / source.name)

        for jvm_dir_name in ("jvm", "jvmlibs", "modules"):
            jvm_dir = python_dir / jvm_dir_name
            if jvm_dir.exists():
                yield PathRefToDest(jvm_dir, dest=lambda self, source: self.bin_dir.parent / source.name)

    @classmethod
    @abstractmethod
    def _native_lib(cls, lib_dir: Path, platform: str) -> Path:
        # Return the path to the native library for this platform.
        raise NotImplementedError

    @classmethod
    def _shared_libs(cls, python_dir: Path) -> Iterator[Path]:
        raise NotImplementedError

    def set_pyenv_cfg(self) -> None:
        """Record the home of the environment, dropping the ``bin`` suffix on GraalPy 24.0 and older."""
        super().set_pyenv_cfg()
        # GraalPy 24.0 and older had home without the bin
        version = self.interpreter.version_info
        # python 3.10 is the last version with the GraalPy home layout that has no bin
        if version.minor <= 10:  # ruff:ignore[magic-value-comparison]
            home = Path(self.pyenv_cfg["home"])
            if home.name == "bin":
                self.pyenv_cfg["home"] = str(home.parent)


class GraalPyPosix(GraalPy, PosixSupports):
    """GraalPy on POSIX platforms."""

    @classmethod
    def _native_lib(cls, lib_dir: Path, platform: str) -> Path:
        if platform == "darwin":
            return lib_dir / "libpythonvm.dylib"
        return lib_dir / "libpythonvm.so"


class GraalPyWindows(GraalPy, WindowsSupports):
    """GraalPy on Windows platforms."""

    @classmethod
    # the base hook signature, the Windows layout has one native library name
    def _native_lib(cls, lib_dir: Path, platform: str) -> Path:  # ruff:ignore[unused-class-method-argument]
        return lib_dir / "pythonvm.dll"

    def set_pyenv_cfg(self) -> None:
        """Record the launcher command in the ``pyvenv.cfg`` file, which GraalPy needs on Windows."""
        # GraalPy needs an additional entry in pyvenv.cfg on Windows
        super().set_pyenv_cfg()
        self.pyenv_cfg["venvlauncher_command"] = self.interpreter.system_exe


__all__ = [
    "GraalPyPosix",
    "GraalPyWindows",
]
