from __future__ import annotations

__lazy_modules__ = [
    "collections",
    "virtualenv.create.describe",
    "virtualenv.create.via_global_ref.builtin.builtin_way",
]

from collections import OrderedDict, defaultdict
from typing import TYPE_CHECKING, NamedTuple, NoReturn

from virtualenv.create.describe import Describe
from virtualenv.create.via_global_ref.builtin.builtin_way import VirtualenvBuiltin

from .base import ComponentBuilder

if TYPE_CHECKING:
    from collections.abc import Sequence

    from python_discovery import PythonInfo

    from virtualenv.config.cli.parser import VirtualEnvConfigParser, VirtualEnvOptions
    from virtualenv.create.creator import Creator, CreatorMeta


class CreatorSelector(ComponentBuilder):
    """Select the creator of the environment from the creators that can handle the interpreter.

    :param interpreter: the interpreter the environment is created from
    :param parser: the parser to add the creator options to

    :var describe: the describer class, ``None`` when no describer applies
    :var builtin_key: the name of the builtin creator
    :var key_to_meta: the capability metadata of each creator, keyed by name

    """

    def __init__(self, interpreter: PythonInfo, parser: VirtualEnvConfigParser) -> None:
        self._parser = parser
        creators, self.key_to_meta, self.describe, self.builtin_key = self.for_interpreter(interpreter)
        # for_interpreter returns dict[str, type[Creator]], the builder types it as dict[str, type]
        super().__init__(interpreter, parser, "creator", creators)  # ty: ignore[invalid-argument-type]

    @classmethod
    def for_interpreter(cls, interpreter: PythonInfo) -> CreatorInfo:
        """Return the creators that can handle the interpreter, with their metadata.

        :param interpreter: the interpreter the environment is created from

        :returns: the creators and their metadata

        :raises RuntimeError: when a creator uses the reserved builtin name or no creator can handle the interpreter

        """
        key_to_class, key_to_meta, builtin_key, describe = OrderedDict(), {}, None, None
        errors = defaultdict(list)
        for key, creator_class in cls.options("virtualenv.create").items():
            if key == "builtin":
                msg = "builtin creator is a reserved name"
                raise RuntimeError(msg)
            # plugin classes come from entry points, which ty sees as type
            meta = creator_class.can_create(interpreter)  # ty: ignore[missing-attribute]
            if meta:
                if meta.error:
                    errors[meta.error].append(creator_class)
                elif cls._add_creator(key, creator_class, meta, key_to_class, key_to_meta):
                    builtin_key = key
            if describe is None and issubclass(creator_class, Describe) and creator_class.can_describe(interpreter):
                describe = creator_class
        if not key_to_meta:
            cls._raise_no_creator(interpreter, errors)
        return CreatorInfo(
            key_to_class=key_to_class,
            key_to_meta=key_to_meta,
            describe=describe,
            builtin_key=builtin_key or "",
        )

    @staticmethod
    def _add_creator(
        key: str,
        creator_class: type,
        meta: CreatorMeta,
        key_to_class: dict[str, type],
        key_to_meta: dict[str, CreatorMeta],
    ) -> bool:
        first_builtin = "builtin" not in key_to_class and issubclass(creator_class, VirtualenvBuiltin)
        if first_builtin:
            key_to_class["builtin"] = creator_class
            key_to_meta["builtin"] = meta
        key_to_class[key] = creator_class
        key_to_meta[key] = meta
        return first_builtin

    @staticmethod
    def _raise_no_creator(interpreter: PythonInfo, errors: defaultdict[str, list[type[Creator]]]) -> NoReturn:
        if errors:
            rows = [f"{k} for creators {', '.join(i.__name__ for i in v)}" for k, v in errors.items()]
            raise RuntimeError("\n".join(rows))
        msg = f"No virtualenv implementation for {interpreter}"
        raise RuntimeError(msg)

    def add_selector_arg_parse(self, name: str, choices: Sequence[str]) -> None:
        # prefer the built-in venv if present, otherwise fallback to first defined type
        """Add the creator option, with the builtin creator first when it is among the choices.

        :param name: the option name
        :param choices: the creator names to choose from

        """
        choices = sorted(choices, key=lambda name: 0 if name == "builtin" else 1)
        default_value = self._get_default(choices)
        self.parser.add_argument(
            f"--{name}",
            choices=choices,
            default=default_value,
            required=False,
            help=f"create environment via{'' if self.builtin_key is None else f' (builtin = {self.builtin_key})'}",
        )

    @staticmethod
    def _get_default(choices: list[str]) -> str:
        return next(iter(choices))

    def _available_for(self) -> str:
        return f" for {self.interpreter.spec}"  # only the creators that support this interpreter are choices

    def populate_selected_argparse(
        self,
        selected: str,
        app_data: object,  # simplint: ignore[imprecise-annotation]  # public signature
    ) -> None:
        """Set the parser description and add the options of the chosen creator.

        :param selected: the name of the chosen creator
        :param app_data: the application data folder

        """
        self.parser.description = f"options for {self.name} {selected}"
        assert self._impl_class is not None  # ruff:ignore[assert]  # Set by handle_selected_arg_parse
        # plugin classes come from entry points, which ty sees as type
        self._impl_class.add_parser_arguments(self.parser, self.interpreter, self.key_to_meta[selected], app_data)  # ty: ignore[missing-attribute]

    def create(self, options: VirtualEnvOptions) -> Creator:
        """Create the creator the options select, checking that a clear is not aimed at a symlink.

        :param options: the parsed options

        :returns: the creator of the environment

        """
        if options.clear and getattr(options, "dest_is_link", False):
            self._parser.error("--clear cannot use a symlink destination; pass the target directory explicitly")
        options.meta = self.key_to_meta[getattr(options, self.name)]
        assert self._impl_class is not None  # ruff:ignore[assert]  # Set by handle_selected_arg_parse
        if not issubclass(self._impl_class, Describe):
            # describe is set by for_interpreter, which ty sees as possibly None
            options.describe = self.describe(options, self.interpreter)  # ty: ignore[not-callable, invalid-argument-type]
        # the builder chain returns object from super().create in ty's view
        return super().create(options)  # ty: ignore[invalid-explicit-return]


class CreatorInfo(NamedTuple):
    """The creators available for an interpreter, with their metadata, the describer and the builtin creator name.

    :param key_to_class: the creator classes keyed by their name
    :param key_to_meta: the capability metadata of each creator, keyed by name
    :param describe: the describer class, ``None`` when no describer applies
    :param builtin_key: the name of the builtin creator

    """

    key_to_class: dict[str, type[Creator]]
    key_to_meta: dict[str, CreatorMeta]
    describe: type[Describe] | None
    builtin_key: str


__all__ = [
    "CreatorInfo",
    "CreatorSelector",
]
