from __future__ import annotations

__lazy_modules__ = [
    "collections",
    "pathlib",
]

from abc import ABC
from collections import OrderedDict
from pathlib import Path
from typing import TYPE_CHECKING

from virtualenv.info import IS_WIN

if TYPE_CHECKING:
    from python_discovery import PythonInfo


class Describe:
    """Given a host interpreter tell us information about what the created interpreter might look like.

    :param dest: the directory the virtual environment is created in
    :param interpreter: the host interpreter the environment is described from

    :var suffix: the executable suffix, ``.exe`` on Windows and empty elsewhere

    """

    suffix = ".exe" if IS_WIN else ""

    def __init__(self, dest: Path, interpreter: PythonInfo) -> None:
        self.interpreter = interpreter
        self.dest = dest
        self._stdlib = None
        self._stdlib_platform = None
        self._conf_vars = None

    @property
    def libs(self) -> list[Path]:
        """The library directories of the environment, platform specific first."""
        return list(OrderedDict(((self.platlib, None), (self.purelib, None))).keys())

    @property
    def platlib(self) -> Path:
        """The platform specific library directory of the environment."""
        return self.dest / self.interpreter.install_path("platlib")

    @property
    def purelib(self) -> Path:
        """The pure Python library directory of the environment."""
        return self.dest / self.interpreter.install_path("purelib")

    @property
    def stdlib(self) -> Path:
        """The standard library directory of the environment."""
        if self._stdlib is None:
            self._stdlib = Path(self.interpreter.sysconfig_path("stdlib", config_var=self._config_vars))
        return self._stdlib

    @property
    def _config_vars(self) -> dict[str, str | int | None]:
        if self._conf_vars is None:
            self._conf_vars = self._calc_config_vars(self.dest)
        return self._conf_vars

    def _calc_config_vars(self, to: Path) -> dict[str, str | int | None]:
        sys_vars = self.interpreter.sysconfig_vars
        if (prefix := self.interpreter.prefix) is None:  # no prefix means no value can live under it
            return dict(sys_vars)
        return {k: (str(to) if isinstance(v, str) and v.startswith(prefix) else v) for k, v in sys_vars.items()}

    @property
    def stdlib_platform(self) -> Path:
        """The platform specific standard library directory of the environment."""
        if self._stdlib_platform is None:
            self._stdlib_platform = Path(self.interpreter.sysconfig_path("platstdlib", config_var=self._config_vars))
        return self._stdlib_platform

    @property
    def env_name(self) -> str:
        """The name of the environment, taken from the last component of its destination."""
        return self.dest.parts[-1]

    @property
    def exe(self) -> Path:
        """The path to the Python executable of the environment."""
        return self.bin_dir / f"{self.exe_stem()}{self.suffix}"

    @property
    def bin_dir(self) -> Path:
        """The directory holding the environment's executables."""
        return self.script_dir

    @property
    def script_dir(self) -> Path:
        """The directory holding the scripts the environment installs."""
        return self.dest / self.interpreter.install_path("scripts")

    @classmethod
    def exe_stem(cls) -> str:
        """Executable name without suffix - there seems to be no standard way to get this without creating it.

        :returns: the executable name without suffix

        """
        raise NotImplementedError

    @classmethod
    # the base hook takes the interpreter, this describer accepts every one
    def can_describe(cls, interpreter: PythonInfo) -> bool:  # ruff:ignore[unused-class-method-argument]
        """Knows means it knows how the output will look.

        :param interpreter: the host interpreter to check

        :returns: ``True`` if the output for this interpreter can be described

        """
        return True

    def script(self, name: str) -> Path:
        """Return the path of a script in the environment's script directory.

        :param name: the script name without suffix

        :returns: the path of the script with the platform suffix

        """
        return self.script_dir / f"{name}{self.suffix}"


class Python3Supports(Describe, ABC):
    """Describer for environments whose interpreter is Python 3."""


class PosixSupports(Describe, ABC):
    """Describer for environments on POSIX hosts."""

    @classmethod
    def can_describe(cls, interpreter: PythonInfo) -> bool:
        """Check the host is POSIX and the base check also accepts it.

        :param interpreter: the host interpreter to check

        :returns: ``True`` if this describer applies to the interpreter

        """
        return interpreter.os == "posix" and super().can_describe(interpreter)


class WindowsSupports(Describe, ABC):
    """Describer for environments on Windows hosts."""

    @classmethod
    def can_describe(cls, interpreter: PythonInfo) -> bool:
        """Check the host is Windows and the base check also accepts it.

        :param interpreter: the host interpreter to check

        :returns: ``True`` if this describer applies to the interpreter

        """
        return interpreter.os == "nt" and super().can_describe(interpreter)


__all__ = [
    "Describe",
    "PosixSupports",
    "Python3Supports",
    "WindowsSupports",
]
