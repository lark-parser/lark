from __future__ import annotations

from typing import TYPE_CHECKING

from .base import PluginLoader

if TYPE_CHECKING:
    from virtualenv.config.cli.parser import VirtualEnvConfigParser
    from virtualenv.discovery.discover import Discover


def get_discover(parser: VirtualEnvConfigParser, args: list[str] | None) -> Discover:
    """Return the discovery of the interpreter, chosen from the installed discovery plugins.

    :param parser: the parser to add the discovery options to
    :param args: the command line arguments

    :returns: the discovery of the interpreter

    :raises RuntimeError: when no discovery plugin is installed

    """
    discover_types = Discovery.entry_points_for("virtualenv.discovery")
    discovery_parser = parser.add_argument_group(
        title="discovery",
        description="discover and provide a target interpreter",
    )
    choices = _get_default_discovery(discover_types)
    # prefer the builtin if present, otherwise fallback to first defined type
    choices = sorted(choices, key=lambda name: 0 if name == "builtin" else 1)
    try:
        default_discovery = next(iter(choices))
    except StopIteration as error:
        msg = "No discovery plugin found. Try reinstalling virtualenv to fix this issue."
        raise RuntimeError(msg) from error
    discovery_parser.add_argument(
        "--discovery",
        choices=choices,
        default=default_discovery,
        required=False,
        help="interpreter discovery method",
    )
    options, _ = parser.parse_known_args(args)
    discovery = options.discovery
    if discovery not in discover_types:
        available = ", ".join(sorted(discover_types))
        msg = (
            f"discovery {discovery!r} is not available. "
            f"Available discovery methods: {available}. "
            f"Is the plugin installed?"
        )
        raise RuntimeError(msg)
    discover_class = discover_types[discovery]
    # plugin classes come from entry points, which ty sees as type
    discover_class.add_parser_arguments(discovery_parser)  # ty: ignore[missing-attribute]
    options, _ = parser.parse_known_args(args, namespace=options)
    return discover_class(options)


class Discovery(PluginLoader):
    """Discovery plugins."""


def _get_default_discovery(discover_types: dict[str, type]) -> list[str]:
    return list(discover_types.keys())


__all__ = [
    "Discovery",
    "get_discover",
]
