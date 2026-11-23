from __future__ import annotations

__lazy_modules__ = [
    "argparse",
    "pathlib",
    "virtualenv.config.cli.parser",
    "virtualenv.seed.wheels",
    "virtualenv.seed.wheels.embed",
]

import logging
from abc import ABC
from argparse import SUPPRESS, ArgumentTypeError
from pathlib import Path
from typing import TYPE_CHECKING, Final

from virtualenv.config.cli.parser import ExtendAction
from virtualenv.seed.seeder import Seeder
from virtualenv.seed.wheels import Version
from virtualenv.seed.wheels.embed import MIN, OLDEST_SUPPORTED

if TYPE_CHECKING:
    from argparse import ArgumentParser

    from python_discovery import PythonInfo

    from virtualenv.app_data.base import AppData
    from virtualenv.config.cli.parser import VirtualEnvOptions

LOGGER: Final[logging.Logger] = logging.getLogger(__name__)  # simplint: ignore[module-variable-prefix]  # existing name
#: Whether the bundled wheels are updated periodically when ``--no-periodic-update`` is not passed. Distributions
#: patch this to ``False`` to let their package manager own the seed wheels, which is why it is a module constant.
PERIODIC_UPDATE_ON_BY_DEFAULT: Final[bool] = True


class BaseEmbed(Seeder, ABC):
    """Base for the seeders that install the bundled pip, setuptools and wheel into the environment.

    :param options: the parsed options

    :var download: ``True`` to download the newest versions from PyPI when no bundled wheel is used
    :var extra_search_dir: the folders searched for extra wheels
    :var pip_version: the pip version to seed, ``None`` when not wanted
    :var setuptools_version: the setuptools version to seed, ``None`` when not wanted
    :var wheel_version: the wheel version to seed, ``None`` when not wanted
    :var no_pip: ``True`` to skip seeding pip
    :var no_setuptools: ``True`` to skip seeding setuptools
    :var no_wheel: ``True`` to skip seeding wheel
    :var app_data: the application data folder
    :var periodic_update: whether the bundled wheels are updated periodically
    :var enabled: ``False`` when seeding is disabled

    """

    def __init__(self, options: VirtualEnvOptions) -> None:
        super().__init__(options, enabled=options.no_seed is False)

        self.download = options.download is True  # unset means no download
        self.extra_search_dir = [i.resolve() for i in options.extra_search_dir if i.is_dir()]

        self.pip_version = options.pip
        self.setuptools_version = options.setuptools

        # virtualenv no longer bundles wheel; the parsed default stays None (unused) so the
        # warning below fires only when you pass --wheel or --no-wheel
        self.wheel_version = options.wheel or "none"

        self.no_pip = options.no_pip
        self.no_setuptools = options.no_setuptools
        self.app_data = options.app_data
        self.periodic_update = not options.no_periodic_update

        if options.wheel is not None or options.no_wheel:
            LOGGER.warning(
                "DEPRECATION: the --wheel and --no-wheel options do nothing; virtualenv no longer bundles wheel. "
                "They will be removed in a release after 2026-12. Stop passing them.",
            )
        self.no_wheel = True

        if not self.distribution_to_versions():
            self.enabled = False

    def distribution_to_versions(self) -> dict[str, str]:
        """The versions of the distributions to seed, keyed by distribution name.

        :returns: the version of each distribution that is not disabled

        """
        return {
            distribution: getattr(self, f"{distribution}_version")
            for distribution in self.distributions()
            if getattr(self, f"no_{distribution}", None) is False and getattr(self, f"{distribution}_version") != "none"
        }

    @classmethod
    def distributions(cls) -> dict[str, str]:
        """The distributions this seeder can install, keyed by name, with the version each defaults to.

        :returns: the default version of each distribution

        """
        return {
            "pip": Version.bundle,
            "setuptools": Version.bundle,
            "wheel": Version.bundle,
        }

    def __repr__(self) -> str:
        result = self.__class__.__name__
        result += "("
        if self.extra_search_dir:
            result += f"extra_search_dir={', '.join(str(i) for i in self.extra_search_dir)},"
        result += f"download={self.download},"
        for distribution in self.distributions():
            if getattr(self, f"no_{distribution}", None):
                continue
            version = getattr(self, f"{distribution}_version", None)
            if version == "none":
                continue
            result += f" {distribution}={version or 'latest'},"
        return f"{result[:-1]})"

    @classmethod
    def cannot_seed(cls, interpreter: PythonInfo) -> str | None:
        """Explain why the bundled wheels cannot seed the target Python version.

        The embedded pip/setuptools stopped shipping for Pythons below :data:`OLDEST_SUPPORTED`, so seeding one would
        install an incompatible wheel.

        :param interpreter: the interpreter to be seeded

        :returns: ``None`` when the bundled wheels still support the target, otherwise a message naming the target and
            the remedies

        """
        if interpreter.version_info[:2] >= OLDEST_SUPPORTED:
            return None
        target = f"{interpreter.version_info.major}.{interpreter.version_info.minor}"
        return (
            f"the bundled seeder no longer ships pip/setuptools for Python {target}; the oldest supported target is "
            f"Python {MIN} - pass --no-seed for an empty environment, use a seeder that provides Python {target} "
            f"wheels, or install an older virtualenv release"
        )

    @classmethod
    # the base hook takes the app data, the embed seeder does not read it
    def add_parser_arguments(cls, parser: ArgumentParser, interpreter: PythonInfo, app_data: AppData) -> None:  # ruff:ignore[unused-class-method-argument]
        """Add the options that control download and the bundled wheels.

        :param parser: the parser to add the options to
        :param interpreter: the interpreter the environment is created from
        :param app_data: the application data folder

        """
        # a tri-state pair like --venv-redirect/--no-venv-redirect: the parser reads a true environment or ini value of
        # either flag as that flag being passed and lets an environment variable beat the ini file; the opt-out comes
        # last so that it wins when both flags are set at the same level
        group = parser.add_mutually_exclusive_group()
        group.add_argument(
            "--download",
            dest="download",
            action="store_const",
            const=True,
            help=f"pass to enable download of the latest {'/'.join(cls.distributions())} from PyPI",
            default=None,
        )
        group.add_argument(
            "--no-download",
            "--never-download",
            dest="download",
            action="store_const",
            const=False,
            help=f"pass to disable download of the latest {'/'.join(cls.distributions())} from PyPI",
            default=None,
        )
        parser.add_argument(
            "--extra-search-dir",
            metavar="d",
            type=cls._search_dir,
            nargs="+",
            action=ExtendAction,
            help="a directory containing wheels to extend the internal wheel list (can be set 1+ times)",
            default=[],
        )
        for distribution, default in cls.distributions().items():
            help_ = f"version of {distribution} to install as seed: embed, bundle, none or exact version"
            if interpreter.version_info[:2] >= (3, 12) and distribution == "setuptools":
                # the default is overridden for setuptools on 3.12+, reusing the loop name is intended
                default = "none"  # ruff:ignore[redefined-loop-name]
            if distribution == "wheel":
                # the default is overridden for wheel, reusing the loop name is intended
                default = None  # ruff:ignore[redefined-loop-name]
                help_ = SUPPRESS
            parser.add_argument(
                f"--{distribution}",
                dest=distribution,
                metavar="version",
                type=_seed_version,
                help=help_,
                default=default,
            )
        for distribution in cls.distributions():
            help_ = f"do not install {distribution}"
            if distribution == "wheel":
                help_ = SUPPRESS
            parser.add_argument(
                f"--no-{distribution}",
                dest=f"no_{distribution}",
                action="store_true",
                help=help_,
                default=False,
            )
        parser.add_argument(
            "--no-periodic-update",
            dest="no_periodic_update",
            action="store_true",
            help="disable the periodic (once every 14 days) update of the embedded wheels",
            default=not PERIODIC_UPDATE_ON_BY_DEFAULT,
        )

    @staticmethod
    def _search_dir(value: str) -> Path:
        if not value:
            msg = "extra search directory cannot be empty"
            raise ArgumentTypeError(msg)
        return Path(value)


def _seed_version(value: str) -> str:
    try:
        return Version.validate(value)
    except ValueError as exception:
        # argparse shows only an ArgumentTypeError's message; a ValueError prints as "invalid _seed_version value"
        raise ArgumentTypeError(str(exception)) from exception


__all__ = [
    "PERIODIC_UPDATE_ON_BY_DEFAULT",
    "BaseEmbed",
]
