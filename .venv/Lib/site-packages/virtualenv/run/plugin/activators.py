from __future__ import annotations

__lazy_modules__ = [
    "argparse",
    "collections",
    "logging",
]

import logging
import os
import sys
from argparse import ArgumentTypeError
from collections import OrderedDict
from typing import TYPE_CHECKING

from .base import ComponentBuilder

if TYPE_CHECKING:
    from collections.abc import Sequence

    from python_discovery import PythonInfo

    from virtualenv.activation.activator import Activator
    from virtualenv.config.cli.parser import VirtualEnvConfigParser, VirtualEnvOptions


class ActivationSelector(ComponentBuilder):
    """Select the activators for the environment, from the defaults and the names given on the command line.

    :param interpreter: the interpreter the environment is created from
    :param parser: the parser to add the activator options to

    :var default: the comma separated names of the default activators
    :var active: the activators selected for the environment, keyed by name

    """

    def __init__(self, interpreter: PythonInfo, parser: VirtualEnvConfigParser) -> None:
        self.default = None
        possible = OrderedDict(
            (k, v)
            for k, v in self.options("virtualenv.activate").items()
            # plugin classes come from entry points, which ty sees as type
            if v.supports(interpreter)  # ty: ignore[missing-attribute]
        )
        super().__init__(interpreter, parser, "activators", possible)
        self.parser.description = "options for activation scripts"
        self.active = None

    def add_selector_arg_parse(self, name: str, choices: Sequence[str]) -> None:
        """Add the option that selects the activators, with the names as the choices.

        :param name: the option name
        :param choices: the activator names to choose from

        """
        self.default = ",".join(choices)
        self.parser.add_argument(
            f"--{name}",
            default=self.default,
            metavar="comma_sep_list",
            required=False,
            help="activators to generate - default is all supported",
            type=self._extract_activators,
        )

    def _extract_activators(self, entered_str: str) -> list[str]:
        # a config file or environment variable may also list the activators on separate lines
        elements = [name for e in ",".join(entered_str.splitlines()).split(",") if (name := e.strip())]
        if missing := [e for e in elements if e not in self.possible]:
            msg = f"the following activators are not available {','.join(missing)}"
            raise ArgumentTypeError(msg)
        return elements

    # returns None, while the base hook returns the selected name as str
    def handle_selected_arg_parse(self, options: VirtualEnvOptions) -> None:  # ty: ignore[incompatible-method-override]
        """Store the activators the options select, falling back to the defaults.

        :param options: the parsed options

        """
        selected_activators = (
            self._extract_activators(self.default) if options.activators is self.default else options.activators
        )
        self.active = {k: v for k, v in self.possible.items() if k in selected_activators}
        self.parser.add_argument(
            "--prompt",
            dest="prompt",
            metavar="prompt",
            help=(
                "provides an alternative prompt prefix for this environment "
                "(value of . means name of the current working directory)"
            ),
            default=None,
        )
        for activator in self.active.values():
            # plugin classes come from entry points, which ty sees as type
            activator.add_parser_arguments(self.parser, self.interpreter)  # ty: ignore[missing-union-attribute]

    def create(self, options: VirtualEnvOptions) -> list[Activator]:
        """Create the activators the options select.

        :param options: the parsed options

        :returns: the activators, in the order they were selected

        :raises ValueError: when the file system cannot encode the destination and only some activators are selected

        """
        assert self.active is not None  # ruff:ignore[assert]  # Set by handle_selected_arg_parse
        if self.active.keys() - {"python"} and os.name != "nt":
            try:
                matches = os.fsencode(options.dest) == options.dest.encode("utf-8")
            except UnicodeEncodeError:
                matches = False
            if not matches:
                msg = (
                    f"the file system codec ({sys.getfilesystemencoding()}) does not encode {options.dest!r} as UTF-8 "
                    "does; activation scripts would point at a different directory"
                )
                # a narrower selection than the default names the shell activators on purpose
                if self.active.keys() != self.possible.keys():
                    raise ValueError(msg)
                logging.getLogger(__name__).warning("skipping shell activation scripts: %s", msg)
                self.active = {name: activator for name, activator in self.active.items() if name == "python"}
        return [activator_class(options) for activator_class in self.active.values()]


__all__ = [
    "ActivationSelector",
]
