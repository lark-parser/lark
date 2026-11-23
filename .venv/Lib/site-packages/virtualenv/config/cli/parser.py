from __future__ import annotations

__lazy_modules__ = [
    "collections",
    "shutil",
    "virtualenv.config.convert",
    "virtualenv.config.env_var",
    "virtualenv.config.ini",
]

import os
import shutil
from argparse import SUPPRESS, Action, ArgumentDefaultsHelpFormatter, ArgumentParser, Namespace
from collections import OrderedDict
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from virtualenv.config.convert import TypeData

from virtualenv.config.convert import get_type
from virtualenv.config.env_var import get_env_var
from virtualenv.config.ini import IniConfig


class ExtendAction(Action):
    """Accumulate CLI groups without including configured defaults."""

    def __call__(
        self,
        parser: ArgumentParser,  # ruff:ignore[unused-method-argument] - required argparse signature
        namespace: Namespace,
        values: Sequence[object] | None,
        option_string: str | None = None,  # ruff:ignore[unused-method-argument] - required argparse signature
    ) -> None:
        options = cast("VirtualEnvOptions", namespace)
        previous = getattr(options, self.dest) if options.get_source(self.dest) == "cli" else []
        setattr(options, self.dest, [*previous, *cast("Sequence[object]", values)])


class VirtualEnvConfigParser(ArgumentParser):
    """Custom option parser which updates its defaults by checking the configuration files and environmental vars.

    :param options: the options to populate, a fresh set of defaults when not given
    :param env: the environment variables to read, the process environment when not given
    :param args: positional arguments passed on to :class:`argparse.ArgumentParser`
    :param kwargs: keyword arguments passed on to :class:`argparse.ArgumentParser`

    :var file_config: the configuration file reader
    :var epilog_list: extra epilog entries, empty unless something appends to it

    """

    def __init__(
        self,
        options: VirtualEnvOptions | None = None,
        env: Mapping[str, str] | None = None,
        *args: Any,  # ruff:ignore[any-type]  # keeps ArgumentParser's open-ended constructor arguments
        **kwargs: Any,  # ruff:ignore[any-type]  # keeps ArgumentParser's open-ended constructor arguments
    ) -> None:
        env = os.environ if env is None else env
        self.file_config = IniConfig(env)
        self.epilog_list = []
        self.env = env
        kwargs["epilog"] = self.file_config.epilog
        kwargs["add_help"] = False
        kwargs["formatter_class"] = HelpFormatter
        kwargs["prog"] = "virtualenv"
        super().__init__(*args, **kwargs)
        self._fixed = set()
        if options is not None and not isinstance(options, VirtualEnvOptions):
            msg = "options must be of type VirtualEnvOptions"
            raise TypeError(msg)
        self.options = VirtualEnvOptions() if options is None else options
        self._interpreter = None
        self._app_data = None

    def enable_help(self) -> None:
        """Add the ``-h`` and ``--help`` options, after fixing the defaults."""
        self._fix_defaults()
        self.add_argument("-h", "--help", action="help", default=SUPPRESS, help="show this help message and exit")

    def _fix_defaults(self) -> None:
        for action in self._actions:
            if (action_id := id(action)) not in self._fixed:
                self._fix_default(action)
                self._fixed.add(action_id)
            elif self.options.get_source(action.dest) == "cli":
                # Each parsing pass starts from the configured default, not the previous CLI values, otherwise
                # accumulating actions (count, append, extend) add the same arguments again on every pass.
                self.options.set_src(action.dest, action.default, getattr(action, "default_source", "default"))

    def _fix_default(self, action: Action) -> None:
        if hasattr(action, "default") and hasattr(action, "dest") and action.default != SUPPRESS:
            as_type = get_type(action)
            names = OrderedDict((i.lstrip("-").replace("-", "_"), None) for i in action.option_strings)
            outcome = self._configured_outcome(names, as_type)
            if tri_state := action.default is None and isinstance(action.const, bool):
                outcome = _as_passed_flag(action.const, outcome)
            # A sibling flag's environment value takes precedence over this flag's configuration file value.
            if outcome is not None and not (
                tri_state and outcome[1] == "file" and self.options.get_source(action.dest) == "env var"
            ):
                action.default, default_source = outcome
                vars(action)["default_source"] = default_source  # simplint: ignore[vars-call]  # argparse metadata  # fmt: skip
            elif tri_state and hasattr(self.options, action.dest):
                return  # a sibling flag sharing this destination already set it
            else:
                outcome = action.default, "default"
            self.options.set_src(action.dest, *outcome)

    def _configured_outcome(
        self, names: Iterable[str], as_type: TypeData
    ) -> tuple[Any, str] | None:  # simplint: ignore[imprecise-annotation]  # type known at run time
        for name in names:
            if (outcome := get_env_var(name, as_type, self.env)) is not None:
                return outcome
        if self.file_config:
            for name in names:
                if (outcome := self.file_config.get(name, as_type)) is not None:
                    return outcome
        return None

    # narrows the base parse_known_args to VirtualEnvOptions, which ty flags as an override
    def parse_known_args(  # ty: ignore[incompatible-method-override]
        self, args: Sequence[str] | None = None, namespace: VirtualEnvOptions | None = None
    ) -> tuple[VirtualEnvOptions, list[str]]:
        """Parse the arguments, filling the options with values from the config file and the environment.

        :param args: the arguments to parse, ``None`` for the command line arguments
        :param namespace: the options to fill, ``None`` for a new set

        :returns: the parsed options and the arguments that were not recognized

        :raises ValueError: when a value from the config file or the environment cannot be converted

        """
        if namespace is None:
            namespace = self.options
        elif namespace is not self.options:
            msg = "can only pass in parser.options"
            raise ValueError(msg)
        self._fix_defaults()
        # the parser records the source of each option on the options object
        self.options._src = "cli"  # ruff:ignore[private-member-access]
        try:
            namespace.env = self.env
            return super().parse_known_args(args, namespace=namespace)
        finally:
            # the parser records the source of each option on the options object
            self.options._src = None  # ruff:ignore[private-member-access]


class HelpFormatter(ArgumentDefaultsHelpFormatter):
    """Help formatter that shows the defaults, sized to the terminal width.

    :param prog: the program name
    :param kwargs: the keyword arguments passed through to the argparse formatter

    """

    # argparse passes its formatter keywords through untyped
    def __init__(self, prog: str, **kwargs: Any) -> None:  # ruff:ignore[any-type]
        super().__init__(prog, max_help_position=32, width=shutil.get_terminal_size().columns, **kwargs)

    def _get_help_string(self, action: Action) -> str | None:
        text = super()._get_help_string(action)
        if text is not None and hasattr(action, "default_source"):
            default = " (default: %(default)s)"
            if text.endswith(default):
                text = f"{text[: -len(default)]} (default: %(default)s -> from %(default_source)s)"
        return text


class VirtualEnvOptions(Namespace):
    """Namespace of the parsed options, with the source each value came from.

    :param kwargs: the option values

    """

    # Namespace takes arbitrary attributes, so the options arrive as kwargs
    def __init__(self, **kwargs: Any) -> None:  # ruff:ignore[any-type]
        super().__init__(**kwargs)
        self._src: str | None = None
        self._sources: dict[str, str] = {}

    # option values have any type, Namespace stores them as-is
    def __setattr__(self, key: str, value: Any) -> None:  # ruff:ignore[any-type]
        if (src := getattr(self, "_src", None)) is not None:
            self._sources[key] = src
        super().__setattr__(key, value)

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}({', '.join(f'{k}={v}' for k, v in self.__dict__.items() if not k.startswith('_'))})"
        )

    @property
    def verbosity(self) -> int | None:
        """The verbosity level, computed as ``verbose - quiet``, clamped to zero.

        The value is ``None`` until either ``--verbose`` or ``--quiet`` has been parsed.

        """
        if not hasattr(self, "verbose") and not hasattr(self, "quiet"):
            return None
        return max(self.verbose - self.quiet, 0)

    # option values have any type, Namespace stores them as-is
    def set_src(self, key: str, value: Any, src: str) -> None:  # ruff:ignore[any-type]
        """Set an option value and record where it came from.

        :param key: the option name
        :param value: the option value
        :param src: the source of the value (e.g. ``"cli"``, ``"env var"``, ``"default"``)

        """
        setattr(self, key, value)
        if src.startswith("env var"):
            src = "env var"
        self._sources[key] = src

    def get_source(self, key: str) -> str | None:
        """Return the source that provided a given option value.

        :param key: the option name

        :returns: the source string (e.g. ``"cli"``, ``"env var"``, ``"default"``), or ``None`` if not tracked

        """
        return self._sources.get(key)


def _as_passed_flag(const: bool, outcome: tuple[bool, str] | None) -> tuple[bool, str] | None:
    # an env var or ini value for a --x/--no-x pair means "as if the flag was passed": true stores the flag's value,
    # while false on the negative flag leaves the choice unset rather than flipping it on
    if outcome is None or const:
        return outcome
    value, source = outcome
    return (False, source) if value else None


__all__ = [
    "ExtendAction",
    "HelpFormatter",
    "VirtualEnvConfigParser",
    "VirtualEnvOptions",
]
