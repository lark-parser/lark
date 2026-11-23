from __future__ import annotations

__lazy_modules__ = [
    "argparse",
    "ast",
    "collections",
    "json",
    "textwrap",
    "virtualenv.util.path",
    "virtualenv.util.subprocess",
    "virtualenv.util.text",
    "virtualenv.version",
    f"{__spec__.parent}.pyenv_cfg",  # ty: ignore[missing-union-attribute]  # imported modules have a spec
]

import json
import logging
import os
import stat
import sys
import textwrap
from abc import ABC, abstractmethod
from argparse import Action, ArgumentTypeError
from ast import literal_eval
from collections import OrderedDict
from pathlib import Path
from typing import TYPE_CHECKING, Final, cast

if TYPE_CHECKING:
    from argparse import ArgumentParser, Namespace
    from collections.abc import Sequence
    from typing import NoReturn

    from python_discovery import PythonInfo

    from virtualenv.app_data.base import AppData
    from virtualenv.config.cli.parser import VirtualEnvOptions

from os.path import commonpath
from typing import Any

from virtualenv.util.path import safe_delete, write_file
from virtualenv.util.subprocess import LogCmd, run_cmd
from virtualenv.util.text import collapse_line_boundaries
from virtualenv.version import __version__

from .pyenv_cfg import PyEnvCfg

#: Directory of this module.
HERE: Final[Path] = Path(os.path.abspath(__file__)).parent
#: Script that reports debug information from an interpreter.
DEBUG_SCRIPT: Final[Path] = HERE / "debug.py"
LOGGER: Final[logging.Logger] = logging.getLogger(__name__)  # simplint: ignore[module-variable-prefix]  # existing name


_DebugInfo = dict[str, Any]


class CreatorMeta:
    """Result of a creator capability check, carrying the reason it cannot create an environment in ``error``.

    :var error: the reason the creator cannot create the environment, ``None`` when it can

    """

    def __init__(self) -> None:
        self.error = None


class Creator(ABC):
    """A class that given a python Interpreter creates a virtual environment.

    :var dest: the directory the virtual environment is created in
    :var clear: ``True`` to delete the destination directory before creating the environment
    :var no_vcs_ignore: ``True`` to skip writing the VCS ignore file into the destination
    :var venv_redirect: ``True`` to always write the ``.venv`` redirect file, ``False`` to never write it, ``None`` to
        write it only beside a project folder that has no ``.venv`` yet
    :var pyenv_cfg: the ``pyvenv.cfg`` of the destination
    :var app_data: the application data folder
    :var env: the environment variables the creation runs with
    :var prompt: the prompt prefix, ``None`` when none was given

    """

    def __init__(self, options: VirtualEnvOptions, interpreter: PythonInfo) -> None:
        """Construct a new virtual environment creator.

        :param options: the CLI option as parsed from :meth:`add_parser_arguments`
        :param interpreter: the interpreter to create virtual environment from

        """
        self.interpreter = interpreter
        self._debug = None
        self.dest = Path(options.dest)
        self.clear = options.clear
        self.no_vcs_ignore = options.no_vcs_ignore
        self.venv_redirect = options.venv_redirect
        self.pyenv_cfg = (
            PyEnvCfg(OrderedDict(), self.dest / "pyvenv.cfg") if self.clear else PyEnvCfg.from_folder(self.dest)
        )
        self.app_data = options.app_data
        self.env = options.env
        self.prompt = getattr(options, "prompt", None)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({', '.join(f'{k}={v}' for k, v in self._args())})"

    def _args(self) -> list[tuple[str, str | bool]]:
        return [
            ("dest", _printable(self.dest)),
            ("clear", self.clear),
            ("no_vcs_ignore", self.no_vcs_ignore),
            ("venv_redirect", self.venv_redirect),
        ]

    if TYPE_CHECKING:

        @property
        def exe(self) -> Path:
            """The path to the Python executable of the environment."""
            ...

        @property
        def env_name(self) -> str:
            """The name of the environment, used in the activation prompt."""
            ...

        @property
        def bin_dir(self) -> Path:
            """The directory holding the environment's executables."""
            ...

        @property
        def script_dir(self) -> Path:
            """The directory holding the scripts the environment installs."""
            ...

        @property
        def libs(self) -> list[Path]:
            """The library directories of the environment."""
            ...

        @property
        def purelib(self) -> Path:
            """The pure Python library directory of the environment."""
            ...

        @property
        def platlib(self) -> Path:
            """The platform specific library directory of the environment."""
            ...

    @property
    def debug(self) -> dict[str, Any] | None:  # simplint: ignore[imprecise-annotation]  # public signature
        """Debug information about the virtual environment (only valid after :meth:`create` has run)."""
        if self._debug is None and self.exe is not None:
            self._debug = get_env_debug_info(self.exe, self.debug_script(), self.app_data, self.env)
        return self._debug

    @staticmethod
    def debug_script() -> Path:
        """Return the path of the script that reports debug information from the environment's interpreter.

        :returns: the path of the debug script

        """
        return DEBUG_SCRIPT

    @classmethod
    # the base hook takes the interpreter, this creator never reads it
    def can_create(cls, interpreter: PythonInfo) -> CreatorMeta | bool | None:  # ruff:ignore[unused-class-method-argument]
        """Determine if we can create a virtual environment.

        :param interpreter: the interpreter in question

        :returns: ``None`` if we can't create, any other object otherwise that will be forwarded to
            :meth:`add_parser_arguments`

        """
        return True

    @classmethod
    def add_parser_arguments(
        cls,
        parser: ArgumentParser,
        # the hook signature is shared by every creator, subclasses read these
        interpreter: PythonInfo,  # ruff:ignore[unused-class-method-argument]
        # the hook signature is shared by every creator, subclasses read these
        meta: CreatorMeta,  # ruff:ignore[unused-class-method-argument]
        # the hook signature is shared by every creator, subclasses read these
        app_data: AppData,  # ruff:ignore[unused-class-method-argument]
    ) -> None:
        """Add CLI arguments for the creator.

        :param parser: the CLI parser
        :param interpreter: the interpreter we're asked to create virtual environment for
        :param meta: value as returned by :meth:`can_create`
        :param app_data: the application data folder

        """

        class Destination(Action):
            def __call__(
                self,
                parser: ArgumentParser,
                namespace: Namespace,
                values: str | Sequence[str] | None,
                option_string: str | None = None,
            ) -> None:
                raw: Final[str] = cast("str", values)
                try:
                    namespace.dest = cls.validate_dest(raw)
                except ArgumentTypeError as exception:
                    parser.error(f"argument {option_string or self.dest}: {exception}")
                destination: Final[Path] = Path(os.path.abspath(raw))
                namespace.dest_is_link = destination.is_symlink() or (
                    os.name == "nt"
                    and destination.exists()
                    and bool(destination.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
                )

        parser.add_argument(
            "dest",
            help="directory to create virtualenv at",
            action=Destination,
        )
        parser.add_argument(
            "--clear",
            dest="clear",
            action="store_true",
            help="remove the destination directory if exist before starting (will overwrite files otherwise)",
            default=False,
        )
        parser.add_argument(
            "--no-vcs-ignore",
            dest="no_vcs_ignore",
            action="store_true",
            help="don't create VCS ignore directive in the destination directory",
            default=False,
        )
        parser.add_argument(
            "--venv-redirect",
            dest="venv_redirect",
            action="store_const",
            const=True,
            help="point a PEP-832 .venv redirect file next to the destination at the created environment, even outside "
            "a project folder; unset, virtualenv does so only beside a pyproject.toml with no .venv yet",
            default=None,
        )
        parser.add_argument(
            "--no-venv-redirect",
            dest="venv_redirect",
            action="store_const",
            const=False,
            help="write no PEP-832 .venv redirect file",
            default=None,
        )

    @classmethod
    def validate_dest(cls, raw_value: str) -> str:
        """Not blank, a directory if it exists, safe for activation, valid chars and must be write-able.

        :param raw_value: the destination as given on the command line

        :returns: the absolute path of the destination

        :raises ArgumentTypeError: when the destination fails any of the checks above

        """
        # an empty value, often an unset shell variable, resolves to the working directory (on Windows so do spaces)
        # and --clear would delete it
        if not raw_value.strip():
            msg = f"destination {raw_value!r} must not be empty or whitespace; pass . to use the current directory"
            raise ArgumentTypeError(msg)
        cls._check_codec(raw_value)
        value = Path(raw_value)
        if value.exists() and not value.is_dir():
            msg = f"the destination {value} already exists and is not a directory"
            raise ArgumentTypeError(msg)
        dest = Path(os.path.abspath(str(value))).resolve()  # on Windows absolute does not imply resolve so use both
        cls._check_activation_path(raw_value, dest)
        cls._ensure_writable(dest)
        return str(dest)

    @staticmethod
    def _check_codec(raw_value: str) -> None:
        # the file system must be able to encode
        # note in newer CPython this is always utf-8 https://www.python.org/dev/peps/pep-0529/
        encoding = sys.getfilesystemencoding()
        refused = OrderedDict()
        kwargs = {"errors": "ignore"} if encoding != "mbcs" else {}
        for char in str(raw_value):
            try:
                trip = char.encode(encoding, **kwargs).decode(encoding)
                if trip == char:
                    continue
                # the ValueError is the signal the except branch records the character with
                raise ValueError(trip)  # ruff:ignore[raise-within-try]
            except ValueError:
                refused[char] = None
        if refused:
            bad = "".join(refused.keys())
            msg = f"the file system codec ({encoding}) cannot handle characters {bad!r} within {raw_value!r}"
            raise ArgumentTypeError(msg)

    @staticmethod
    def _check_activation_path(raw_value: str, dest: Path) -> None:
        resolved = str(dest)
        for destination in (raw_value, resolved):
            if os.pathsep in destination:
                msg = (
                    f"destination {destination!r} must not contain the path separator ({os.pathsep})"
                    f" as this would break the activation scripts"
                )
                raise ArgumentTypeError(msg)
        # dash reads the first percent sign in a PATH entry as an option delimiter.
        # Git for Windows ships dash too, and MSYS keeps the % in the converted PATH entry.
        if resolved.partition("%")[2].startswith(("func", "builtin")):
            msg = f"destination {resolved!r} must not contain a shell PATH option (%func or %builtin)"
            raise ArgumentTypeError(msg)

    @classmethod
    def _ensure_writable(cls, dest: Path) -> None:
        current = dest
        while current:
            if current.exists():
                if current.is_dir() and os.access(str(current), os.W_OK):
                    break
                cls._non_write_able(current, dest)
            base = current.parent
            if base == current:
                # reached only when current is the filesystem root, which tests cannot create
                cls._non_write_able(current, dest)  # pragma: no cover
            current = base

    @staticmethod
    def _non_write_able(dest: Path, value: Path) -> NoReturn:
        if dest.exists() and not dest.is_dir():
            msg = f"the destination {value} is inside {dest}, which is not a directory"
            raise ArgumentTypeError(msg)
        common = Path(commonpath([str(value), str(dest)]))
        msg = f"the destination {dest.relative_to(common)} is not write-able at {common}"
        raise ArgumentTypeError(msg)

    def run(self) -> None:
        """Create the environment and write its metadata, ignore file and ``.venv`` redirect.

        Delete the destination first when it exists and clearing was requested.

        """
        # The stdlib creator and --clear can modify the destination before the final configuration is written.
        self.set_pyenv_cfg()
        self.pyenv_cfg.serialize()
        if self.dest.exists() and self.clear:
            LOGGER.debug("delete %s", self.dest)
            safe_delete(self.dest)
        self.create()
        self.add_cachedir_tag()
        self.set_pyenv_cfg()
        if not self.no_vcs_ignore:
            self.setup_ignore_vcs()
        if self.venv_redirect is not False:
            self.point_venv_redirect()

    def set_pyenv_cfg(self) -> None:
        """Fill the ``pyvenv.cfg`` content with the home, implementation and version of the host interpreter."""
        self.pyenv_cfg.content = OrderedDict()
        system_executable = self.interpreter.system_executable or self.interpreter.executable
        # a PythonInfo always has an executable, the assert narrows the optional type
        assert system_executable is not None  # ruff:ignore[assert]
        self.pyenv_cfg["home"] = os.path.dirname(os.path.abspath(system_executable))
        self.pyenv_cfg["implementation"] = self.interpreter.implementation
        version_info = self.interpreter.version_info
        self.pyenv_cfg["python-version"] = f"{version_info.major}.{version_info.minor}"
        self.pyenv_cfg["version_info"] = ".".join(str(i) for i in version_info)
        self.pyenv_cfg["version"] = ".".join(str(i) for i in version_info[:3])
        self.pyenv_cfg["executable"] = os.path.realpath(system_executable)
        self.pyenv_cfg["command"] = f"{sys.executable} -m virtualenv {self.dest}"
        self.pyenv_cfg["virtualenv"] = __version__
        if self.prompt is not None:
            self.pyenv_cfg["prompt"] = os.path.basename(os.getcwd()) if self.prompt == "." else self.prompt

    @abstractmethod
    def create(self) -> None:
        """Perform the virtual environment creation."""
        raise NotImplementedError

    def add_cachedir_tag(self) -> None:
        """Generate a file indicating that this is not meant to be backed up."""
        cachedir_tag_file = self.dest / "CACHEDIR.TAG"
        if not cachedir_tag_file.exists():
            cachedir_tag_text = textwrap.dedent("""
                Signature: 8a477f597d28d172789f06886806bc55
                # This file is a cache directory tag created by Python virtualenv.
                # For information about cache directory tags, see:
                #   https://bford.info/cachedir/
            """).strip()
            write_file(cachedir_tag_file, cachedir_tag_text.encode("utf-8"))

    def setup_ignore_vcs(self) -> None:
        """Generate ignore instructions for version control systems."""
        # mark this folder to be ignored by VCS, handle https://www.python.org/dev/peps/pep-0610/#registered-vcs
        git_ignore = self.dest / ".gitignore"
        if not git_ignore.exists():
            write_file(git_ignore, b"# created by virtualenv automatically\n*\n")
        # Mercurial - does not support the .hgignore file inside a subdirectory directly, but only if included via the
        # subinclude directive from root, at which point on might as well ignore the directory itself, see
        # https://www.selenic.com/mercurial/hgignore.5.html for more details
        # Bazaar - does not support ignore files in sub-directories, only at root level via .bzrignore
        # Subversion - does not support ignore files, requires direct manipulation with the svn tool

    def point_venv_redirect(self) -> None:
        """Point the ``.venv`` redirect file of the parent folder at the environment, per PEP-832 (provisional)."""
        if self.dest.name == ".venv":  # the environment is the .venv itself, no redirect needed
            return
        redirect = self.dest.parent / ".venv"
        if self.venv_redirect is None and (
            redirect.exists() or redirect.is_symlink() or not (self.dest.parent / "pyproject.toml").is_file()
        ):  # unset: claim the default only for a project folder that has none yet
            return
        if redirect.is_symlink() or redirect.is_dir():
            LOGGER.debug("%s keeps being the default environment", redirect)
            return
        if redirect.exists() and not self._points_at_virtualenv(redirect):
            LOGGER.debug("%s points at an environment virtualenv did not create, leaving it", redirect)
            return
        if collapse_line_boundaries(self.dest.name) != self.dest.name or self.dest.name != self.dest.name.strip():
            LOGGER.warning(
                "could not point %s at %s - the name contains a line boundary or surrounding whitespace",
                _printable(redirect),
                _printable(self.dest),
            )
            return
        try:
            write_file(redirect, f"{self.dest.name}\n".encode())
        except OSError as exc:
            LOGGER.warning("could not point %s at %s - %s", _printable(redirect), _printable(self.dest), exc)

    @staticmethod
    def _points_at_virtualenv(redirect: Path) -> bool:
        if not redirect.is_file():  # only a regular file holds a redirect, and opening a FIFO would wait for a writer
            return False
        try:
            # Universal newlines already turned \r\n into \n.
            line: Final[str] = redirect.read_text(encoding="utf-8").removesuffix("\n")
            return bool(line) and "virtualenv" in PyEnvCfg.from_folder(redirect.parent / line)
        except (OSError, ValueError):  # unreadable, so not a redirect virtualenv can claim
            return False


def _printable(path: Path) -> str:
    text = str(path)
    return text if text.isprintable() else repr(text)


def get_env_debug_info(
    env_exe: Path, debug_script: Path, app_data: AppData, env: dict[str, str]
) -> dict[str, Any]:  # simplint: ignore[imprecise-annotation]  # public signature
    """Run the debug script with the interpreter at ``env_exe`` and return the report it prints.

    :param env_exe: the interpreter to run the script with
    :param debug_script: the script that reports the debug information
    :param app_data: the application data folder
    :param env: the environment variables to run with

    :returns: the debug information

    """  # simplint: ignore[function-docstring]  # existing docs
    env = env.copy()
    env.pop("PYTHONPATH", None)

    with app_data.ensure_extracted(debug_script) as debug_script_extracted:
        cmd = [str(env_exe), str(debug_script_extracted)]
        LOGGER.debug("debug via %r", LogCmd(cmd))
        code, out, err = run_cmd(cmd, env)

    try:
        return _parse_debug_output(code, out, err)
    # a failure to parse the debug output is reported with the raw streams instead
    except Exception as exception:  # ruff:ignore[blind-except]
        return {"out": out, "err": err, "returncode": code, "exception": repr(exception)}


def _parse_debug_output(code: int, out: str, err: str) -> _DebugInfo:
    if code != 0:
        if out:
            result = literal_eval(out)
        # exit status 2 is what python reports for a missing script file
        elif code == 2 and "file" in err:  # ruff:ignore[magic-value-comparison]
            raise OSError(err)
        else:
            # any other failure of the debug script has no narrower exception
            raise Exception(err)  # ruff:ignore[raise-vanilla-class]
    else:
        result = json.loads(out)
    if err:
        result["err"] = err
    return result


__all__ = [
    "Creator",
    "CreatorMeta",
]
