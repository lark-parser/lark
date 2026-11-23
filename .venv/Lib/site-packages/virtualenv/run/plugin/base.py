from __future__ import annotations

__lazy_modules__ = [
    "collections",
    "importlib.metadata",
]

import sys
from collections import OrderedDict
from importlib.metadata import entry_points
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Sequence

    from python_discovery import PythonInfo

    from virtualenv.config.cli.parser import VirtualEnvConfigParser, VirtualEnvOptions


class PluginLoader:
    """Load the plugin classes registered under the entry point groups."""

    _OPTIONS = None
    _ENTRY_POINTS = None

    @classmethod
    def entry_points_for(cls, key: str) -> OrderedDict[str, type]:
        """Return the plugin classes registered under an entry point group.

        :param key: the entry point group name

        :returns: the plugin classes keyed by their entry point name

        """
        if sys.version_info >= (3, 10):
            # ty on Python 3.10 and 3.15 types entry_points() as object, which has no select
            selected = list(cls.entry_points().select(group=key))  # ty: ignore[missing-attribute]
        else:
            # ty on Python 3.9 types entry_points() as object, which has no get
            selected = list(cls.entry_points().get(key, []))  # ty: ignore[missing-attribute]
        # Third-party packages may register entry points with the same name as virtualenv's
        # built-ins (e.g. xonsh's own `virtualenv.activate.xonsh`). Sort so built-ins are
        # inserted last into the OrderedDict, making them win on name collision.
        selected.sort(key=lambda entry: entry.value.startswith("virtualenv."))
        return OrderedDict((e.name, e.load()) for e in selected)

    @staticmethod
    def entry_points() -> object:  # simplint: ignore[imprecise-annotation]  # importlib.metadata type varies by Python
        """Return the entry points of all installed packages, loaded once per process.

        :returns: the entry points

        """
        if PluginLoader._ENTRY_POINTS is None:
            PluginLoader._ENTRY_POINTS = entry_points()
        return PluginLoader._ENTRY_POINTS


class ComponentBuilder(PluginLoader):
    """Build the plugin choice for one component type, with the options of the chosen plugin.

    :param interpreter: the interpreter the environment is created from
    :param parser: the parser to add the options to
    :param name: the component type name, used as the option name
    :param possible: the plugin classes keyed by their name

    :var name: the component type name
    :var possible: the plugin classes keyed by their name

    """

    def __init__(
        self, interpreter: PythonInfo, parser: VirtualEnvConfigParser, name: str, possible: dict[str, type]
    ) -> None:
        self.interpreter = interpreter
        self.name = name
        self._impl_class = None
        self.possible = possible
        self.parser = parser.add_argument_group(title=name)
        self.add_selector_arg_parse(name, list(self.possible))

    def add_selector_arg_parse(self, name: str, choices: Sequence[str]) -> None:
        """Add the option that selects the plugin, to be implemented by subclasses.

        :param name: the option name
        :param choices: the plugin names to choose from

        :raises NotImplementedError: always, subclasses implement it

        """
        raise NotImplementedError

    @classmethod
    def options(cls, key: str) -> OrderedDict[str, type]:
        """Return the options of the plugin type, loaded once per process.

        :param key: the entry point group name

        :returns: the plugin classes keyed by their name

        """
        if cls._OPTIONS is None:
            cls._OPTIONS = cls.entry_points_for(key)
        return cls._OPTIONS

    def handle_selected_arg_parse(self, options: VirtualEnvOptions) -> str:
        """Validate the selected plugin name, load its options and return it.

        :param options: the parsed options

        :returns: the selected plugin name

        :raises RuntimeError: when the selected plugin is not installed

        """
        selected = getattr(options, self.name)
        if selected not in self.possible:
            # argparse checks choices only on the command line, so a value from an env var or ini file can land here
            msg: Final[str] = (
                f"{self.name} {selected!r} is not available{self._available_for()}. "
                f"Available {self.name}s: {', '.join(sorted(self.possible))}. Is the plugin installed?"
            )
            raise RuntimeError(msg)
        self._impl_class = self.possible[selected]
        self.populate_selected_argparse(selected, options.app_data)
        return selected

    def _available_for(self) -> str:
        return ""

    def populate_selected_argparse(
        self,
        selected: str,
        app_data: object,  # simplint: ignore[imprecise-annotation]  # public signature
    ) -> None:
        """Set the parser description and create the chosen plugin's options.

        :param selected: the selected plugin name
        :param app_data: the application data folder

        """
        self.parser.description = f"options for {self.name} {selected}"
        assert self._impl_class is not None  # ruff:ignore[assert]  # Set by handle_selected_arg_parse
        # plugin classes come from entry points, which ty sees as type
        self._impl_class.add_parser_arguments(self.parser, self.interpreter, app_data)  # ty: ignore[missing-attribute]

    def create(
        self, options: VirtualEnvOptions
    ) -> object:  # simplint: ignore[imprecise-annotation]  # entry point class instance, type known at run time
        """Create the chosen plugin.

        :param options: the parsed options

        :returns: the plugin instance

        """
        assert self._impl_class is not None  # ruff:ignore[assert]  # Set by handle_selected_arg_parse
        return self._impl_class(options, self.interpreter)


__all__ = [
    "ComponentBuilder",
    "PluginLoader",
]
