from __future__ import annotations

__lazy_modules__ = [
    "json",
    "typing_extensions",
    "virtualenv.activation.batch",
    "virtualenv.config.cli.parser",
]

import json
import logging
import sys
from typing import TYPE_CHECKING, Final

from virtualenv.activation.batch import BatchActivator
from virtualenv.config.cli.parser import VirtualEnvOptions

if TYPE_CHECKING:
    from types import TracebackType

    from python_discovery import PythonInfo

    from virtualenv.activation.activator import Activator
    from virtualenv.app_data.base import AppData
    from virtualenv.create.creator import Creator
    from virtualenv.seed.seeder import Seeder

if sys.version_info >= (3, 11):
    from typing import Self
else:
    from typing_extensions import Self

LOGGER: Final[logging.Logger] = logging.getLogger(__name__)  # simplint: ignore[module-variable-prefix]  # existing name


class Session:
    """Represents a virtual environment creation session.

    :param verbosity: the verbosity level the creation runs with
    :param app_data: the application data folder
    :param interpreter: the host interpreter the environment is based on
    :param creator: the creator that builds the environment
    :param seeder: the seeder that installs the seed packages
    :param activators: the activators that generate the activation scripts

    """

    # the session keeps each component of a creation as its own argument
    def __init__(  # ruff:ignore[too-many-arguments]
        self,
        verbosity: int,
        app_data: AppData,
        interpreter: PythonInfo,
        creator: Creator,
        seeder: Seeder,
        activators: list[Activator],
    ) -> None:
        self._verbosity = verbosity
        self._app_data = app_data
        self._interpreter = interpreter
        self._creator = creator
        self._seeder = seeder
        self._activators = activators

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self._app_data.close()

    @property
    def verbosity(self) -> int:
        """The verbosity of the run."""
        return self._verbosity

    def run(self) -> None:
        """Create the environment, seed it, activate it and write its configuration file."""
        self._create()
        self._seed()
        self._activate()
        self.creator.pyenv_cfg.write()

    def _create(self) -> None:
        LOGGER.info("create virtual environment via %s", self.creator)
        self.creator.run()
        LOGGER.debug(_DEBUG_MARKER)
        LOGGER.debug("%s", _Debug(self.creator))

    def _seed(self) -> None:
        if self.seeder is not None and self.seeder.enabled:
            LOGGER.info("add seed packages via %s", self.seeder)
            self.seeder.run(self.creator)

    @property
    def seeder(self) -> Seeder:
        """The mechanism used to provide the seed packages (pip, setuptools, wheel)."""
        return self._seeder

    def _activate(self) -> None:
        if BatchActivator.supports(self.interpreter) and not any(
            isinstance(i, BatchActivator) for i in self.activators
        ):
            BatchActivator(VirtualEnvOptions(prompt=None)).remove_unsafe(self.creator, selected=False)
        if self.activators:
            active = ", ".join(type(i).__name__.replace("Activator", "") for i in self.activators)
            LOGGER.info("add activators for %s", active)
            self._activators = [activator for activator in self.activators if activator.generate(self.creator)]

    @property
    def interpreter(self) -> PythonInfo:
        """Create a virtual environment based on this reference interpreter."""
        return self._interpreter

    @property
    def activators(self) -> list[Activator]:
        """Activators used to generate activations scripts."""
        return self._activators

    @property
    def creator(self) -> Creator:
        """The creator used to build the virtual environment (must be compatible with the interpreter)."""
        return self._creator


class _Debug:
    def __init__(self, creator: Creator) -> None:
        self.creator = creator

    def __repr__(self) -> str:
        return json.dumps(self.creator.debug, indent=2)


_DEBUG_MARKER: Final[str] = f"{'=' * 30} target debug {'=' * 30}"


__all__ = [
    "Session",
]
