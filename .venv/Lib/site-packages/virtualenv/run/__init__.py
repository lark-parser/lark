from __future__ import annotations

__lazy_modules__ = [
    "argparse",
    "functools",
    "logging",
    "virtualenv.app_data",
    "virtualenv.config.cli.parser",
    "virtualenv.report",
    "virtualenv.seed.wheels.periodic_update",
    "virtualenv.version",
    f"{__spec__.parent}.plugin.activators",  # ty: ignore[missing-union-attribute]  # imported modules have a spec
    f"{__spec__.parent}.plugin.creators",  # ty: ignore[missing-union-attribute]  # imported modules have a spec
    f"{__spec__.parent}.plugin.discovery",  # ty: ignore[missing-union-attribute]  # imported modules have a spec
    f"{__spec__.parent}.plugin.seeders",  # ty: ignore[missing-union-attribute]  # imported modules have a spec
    f"{__spec__.parent}.session",  # ty: ignore[missing-union-attribute]  # imported modules have a spec
]

import logging
import os
from argparse import SUPPRESS, ArgumentParser
from functools import partial
from typing import TYPE_CHECKING, Final

from virtualenv.app_data import make_app_data as make_app_data
from virtualenv.config.cli.parser import VirtualEnvConfigParser as VirtualEnvConfigParser
from virtualenv.config.cli.parser import VirtualEnvOptions as VirtualEnvOptions
from virtualenv.report import LEVELS as LEVELS
from virtualenv.report import setup_report as setup_report
from virtualenv.seed.wheels.periodic_update import manual_upgrade as manual_upgrade
from virtualenv.version import __version__ as __version__

from .plugin.activators import ActivationSelector as ActivationSelector
from .plugin.creators import CreatorSelector as CreatorSelector
from .plugin.discovery import get_discover as get_discover
from .plugin.seeders import SeederSelector as SeederSelector
from .session import Session as Session

if TYPE_CHECKING:
    from argparse import Action
    from collections.abc import MutableMapping

    from .plugin.base import ComponentBuilder


def cli_run(
    args: list[str],
    options: VirtualEnvOptions | None = None,
    # setup_logging keeps its default for existing callers
    setup_logging: bool = True,  # ruff:ignore[boolean-default-value-positional-argument]
    env: MutableMapping[str, str] | None = None,
) -> Session:
    """Create a virtual environment given some command line interface arguments.

    :param args: the command line arguments
    :param options: passing in a ``VirtualEnvOptions`` object allows return of the parsed options
    :param setup_logging: ``True`` if setup logging handlers, ``False`` to use handlers already registered
    :param env: environment variables to use

    :returns: the session object of the creation (its structure for now is experimental and might change on short
        notice)

    """
    env = os.environ if env is None else env
    of_session = session_via_cli(args, options, setup_logging, env)
    with of_session:
        of_session.run()
    return of_session


def session_via_cli(
    args: list[str],
    options: VirtualEnvOptions | None = None,
    # setup_logging keeps its default for existing callers
    setup_logging: bool = True,  # ruff:ignore[boolean-default-value-positional-argument]
    env: MutableMapping[str, str] | None = None,
) -> Session:
    """Create a virtualenv session, the same as cli_run but without performing the creation.

    Use this if you just want to query what the virtual environment would look like, but not actually create it.

    :param args: the command line arguments
    :param options: passing in a ``VirtualEnvOptions`` object allows return of the parsed options
    :param setup_logging: ``True`` if setup logging handlers, ``False`` to use handlers already registered
    :param env: environment variables to use

    :returns: the session object of the creation (its structure for now is experimental and might change on short
        notice)

    """
    env = os.environ if env is None else env
    parser, elements = build_parser(args, options, setup_logging, env)
    # parse_args returns a plain Namespace, not the VirtualEnvOptions it is typed as
    options = parser.parse_args(args)  # ty: ignore[invalid-assignment]
    # the parser carries the discovered interpreter to the session, which ty cannot see
    options.py_version = parser._interpreter.version_info  # ruff:ignore[private-member-access]  # ty: ignore[invalid-assignment, missing-union-attribute]
    creator, seeder, activators = tuple(
        # options is set by parse_args above, ty still sees the optional type
        e.create(options)  # ty: ignore[invalid-argument-type]
        for e in elements
    )  # create types
    return Session(
        # options is set by parse_args above, ty still sees the optional type
        options.verbosity,  # ty: ignore[missing-union-attribute, invalid-argument-type]
        # options is set by parse_args above, ty still sees the optional type
        options.app_data,  # ty: ignore[missing-union-attribute]
        # the parser carries the discovered interpreter to the session, which ty cannot see
        parser._interpreter,  # ruff:ignore[private-member-access]  # ty: ignore[invalid-argument-type]
        # the builders are untyped, so their create results are object to ty
        creator,  # ty: ignore[invalid-argument-type]
        # the builders are untyped, so their create results are object to ty
        seeder,  # ty: ignore[invalid-argument-type]
        # the builders are untyped, so their create results are object to ty
        activators,  # ty: ignore[invalid-argument-type]
    )


def build_parser(
    args: list[str] | None = None,
    options: VirtualEnvOptions | None = None,
    # setup_logging keeps its default for existing callers
    setup_logging: bool = True,  # ruff:ignore[boolean-default-value-positional-argument]
    env: MutableMapping[str, str] | None = None,
) -> tuple[VirtualEnvConfigParser, list[ComponentBuilder]]:
    """Build the command line parser, with the options and the component options of every plugin.

    :param args: the command line arguments, ``None`` for the process arguments
    :param options: the options to populate, a fresh set when not given
    :param setup_logging: ``True`` to set up the logging of the run, ``False`` to keep the existing one
    :param env: the environment variables, ``None`` for the process environment

    :returns: the parser and the component builders that add their own options

    :raises RuntimeError: when no interpreter matches the discovery options

    """
    _validate_option_values(args)
    parser = VirtualEnvConfigParser(options, os.environ if env is None else env)
    add_version_flag(parser)
    parser.add_argument(
        "--with-traceback",
        dest="with_traceback",
        action="store_true",
        default=False,
        help="on failure also display the stacktrace internals of virtualenv",
    )
    _do_report_setup(parser, args, setup_logging)
    options = load_app_data(args, parser, options)
    handle_extra_commands(options)

    discover = get_discover(parser, args)
    # the parser carries the discovered interpreter to the session
    parser._interpreter = interpreter = discover.interpreter  # ruff:ignore[private-member-access]
    if interpreter is None:
        msg = f"failed to find interpreter for {discover}"
        raise RuntimeError(msg)
    elements: list[ComponentBuilder] = [
        CreatorSelector(interpreter, parser),
        SeederSelector(interpreter, parser),
        ActivationSelector(interpreter, parser),
    ]
    options, _ = parser.parse_known_args(args)
    for element in elements:
        element.handle_selected_arg_parse(options)
    parser.enable_help()
    return parser, elements


def _validate_option_values(args: list[str] | None) -> None:
    # Staged parsing can act on later options before noticing that an earlier option lacks its value.
    # This parser covers only early options, so its usage text would misdescribe the command.
    parser: Final[ArgumentParser] = ArgumentParser(prog="virtualenv", add_help=False, usage=SUPPRESS)
    parser.add_argument("-v", "-q", action="count")
    for option in (
        "--app-data",
        "--discovery",
        "-p",
        "--python",
        "--try-first-with",
        "--creator",
        "--seeder",
        "--activators",
        "--extra-search-dir",
        "--pip",
        "--setuptools",
        "--wheel",
        "--prompt",
    ):
        parser.add_argument(option)
    parser.parse_known_args(args)


def add_version_flag(parser: VirtualEnvConfigParser) -> None:
    """Add the ``--version`` flag, which prints the version and exits.

    :param parser: the parser to add the flag to

    """
    # virtualenv imports this module, so the import waits until the parser is built
    import virtualenv  # ruff:ignore[import-outside-top-level]

    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__} from {virtualenv.__file__}",
        help="display the version of the virtualenv package and its location, then exit",
    )


def _do_report_setup(parser: VirtualEnvConfigParser, args: list[str] | None, setup_logging: bool) -> None:
    level_map = ", ".join(f"{logging.getLevelName(line)}={c}" for c, line in sorted(LEVELS.items()))
    msg = "verbosity = verbose - quiet, default {}, mapping => {}"
    verbosity_group = parser.add_argument_group(
        title="verbosity",
        description=msg.format(logging.getLevelName(LEVELS[3]), level_map),
    )
    verbosity = verbosity_group.add_mutually_exclusive_group()
    verbosity.add_argument("-v", "--verbose", action="count", dest="verbose", help="increase verbosity", default=2)
    verbosity.add_argument("-q", "--quiet", action="count", dest="quiet", help="decrease verbosity", default=0)
    # do not configure logging if only help is requested, as no logging is required for this
    if args and any(i in args for i in ("-h", "--help")):
        return
    option, _ = parser.parse_known_args(args)
    if setup_logging:
        # verbosity is int | None until the parser has parsed the flags
        setup_report(option.verbosity)  # ty: ignore[invalid-argument-type]


def load_app_data(
    args: list[str] | None, parser: VirtualEnvConfigParser, options: VirtualEnvOptions | None
) -> VirtualEnvOptions:
    """Add the app data options and return the options with the app data folder set.

    :param args: the command line arguments
    :param parser: the parser to read the options from
    :param options: the options to populate, ``None`` for a fresh set

    :returns: the populated options

    """
    parser.add_argument(
        "--read-only-app-data",
        action="store_true",
        help="use app data folder in read-only mode (write operations will fail with error)",
    )
    options, _ = parser.parse_known_args(args, namespace=options)

    # here we need a write-able application data (e.g. the zipapp might need this for discovery cache)
    app_data: Final[Action] = parser.add_argument(
        "--app-data",
        help="a data folder used as cache by the virtualenv",
        type=partial(make_app_data, read_only=options.read_only_app_data, env=options.env),
        default=None,
    )
    parser.add_argument(
        "--reset-app-data",
        action="store_true",
        help="start with empty app data folder",
    )
    parser.add_argument(
        "--upgrade-embed-wheels",
        action="store_true",
        help="trigger a manual update of the embedded wheels",
    )
    options, _ = parser.parse_known_args(args, namespace=options)
    if options.app_data is None:
        # build the default only when no folder was given, since building it creates the folder or, when read-only,
        # requires it to exist; it is also stored on the action so that --help still shows it
        options.app_data = app_data.default = make_app_data(None, read_only=options.read_only_app_data, env=options.env)
    if options.reset_app_data:
        options.app_data.reset()
    return options


def handle_extra_commands(options: VirtualEnvOptions) -> None:
    """Run the extra commands that exit once they finish, such as the embedded wheel upgrade.

    :param options: the parsed options

    :raises SystemExit: with the result of the extra command, after it runs

    """
    if options.upgrade_embed_wheels:
        result = manual_upgrade(options.app_data, options.env)
        raise SystemExit(result)


def build_parser_only(args: list[str] | None = None) -> VirtualEnvConfigParser:
    """Used to provide a parser for the doc generation.

    :param args: the command line arguments to parse the configuration with

    :returns: the configured parser, without the component builders

    """
    return build_parser(args)[0]


__all__ = [
    "cli_run",
    "session_via_cli",
]
