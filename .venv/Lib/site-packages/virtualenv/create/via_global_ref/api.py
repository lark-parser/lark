from __future__ import annotations

__lazy_modules__ = [
    "pathlib",
    "virtualenv.info",
    "virtualenv.util.path",
]

import logging
from abc import ABC
from pathlib import Path
from typing import TYPE_CHECKING, Final

from virtualenv.create.creator import Creator, CreatorMeta
from virtualenv.info import fs_supports_symlink
from virtualenv.util.path import write_file

if TYPE_CHECKING:
    from argparse import ArgumentParser

    from python_discovery import PythonInfo

    from virtualenv.app_data.base import AppData
    from virtualenv.config.cli.parser import VirtualEnvOptions

LOGGER: Final[logging.Logger] = logging.getLogger(__name__)  # simplint: ignore[module-variable-prefix]  # existing name


class ViaGlobalRefMeta(CreatorMeta):
    """Capability metadata for creators that link to or copy a global interpreter.

    The errors of a failed symlink or copy check are kept in ``symlink_error`` and ``copy_error``.

    :var copy_error: the reason the files cannot be copied, ``None`` when they can
    :var symlink_error: the reason the files cannot be symlinked, ``None`` when they can

    """

    def __init__(self) -> None:
        super().__init__()
        self.copy_error = None
        self.symlink_error = None
        if not fs_supports_symlink():
            self.symlink_error = "the filesystem does not supports symlink"

    @property
    def can_copy(self) -> bool:
        """Whether the environment can be created by copying files."""
        return not self.copy_error

    @property
    def can_symlink(self) -> bool:
        """Whether the environment can be created by symlinking files."""
        return not self.symlink_error


class ViaGlobalRefApi(Creator, ABC):
    """Base for creators that build an environment from files of a global interpreter, linking or copying them.

    :param options: the parsed command line options
    :param interpreter: the interpreter the environment is created from

    :var symlinks: ``True`` to link files instead of copying them
    :var enable_system_site_package: ``True`` to give the environment access to the system site-packages

    """

    def __init__(self, options: VirtualEnvOptions, interpreter: PythonInfo) -> None:
        super().__init__(options, interpreter)
        self.symlinks = self._should_symlink(options)
        self.enable_system_site_package = options.system_site

    @staticmethod
    def _should_symlink(options: VirtualEnvOptions) -> bool:
        # Priority of where the option is set to follow the order: CLI, env var, file, hardcoded.
        # If both set at same level prefers copy over symlink.
        copies, symlinks = getattr(options, "copies", False), getattr(options, "symlinks", False)
        copy_src, sym_src = options.get_source("copies"), options.get_source("symlinks")
        for level in ["cli", "env var", "file", "default"]:
            s_opt = symlinks if sym_src == level else None
            c_opt = copies if copy_src == level else None
            if s_opt is True and c_opt is True:
                return False
            if s_opt is True:
                return True
            if c_opt is True:
                return False
        return False  # fallback to copy

    if TYPE_CHECKING:

        @property
        def purelib(self) -> Path:
            """The pure Python library directory of the environment."""
            ...

        @property
        def script_dir(self) -> Path:
            """The directory holding the scripts the environment installs."""
            ...

    @classmethod
    def add_parser_arguments(
        cls,
        parser: ArgumentParser,
        interpreter: PythonInfo,
        meta: ViaGlobalRefMeta,
        app_data: AppData,
        # narrows meta to ViaGlobalRefMeta, which the base hook types as CreatorMeta
    ) -> None:  # ty: ignore[incompatible-method-override]
        """Add the ``--system-site-packages``, ``--symlinks`` and ``--copies`` options.

        The copy and symlink options are only added when the matching method is supported.

        :param parser: the parser to add the options to
        :param interpreter: the interpreter the environment is created from
        :param meta: the capability metadata of the interpreter
        :param app_data: the application data folder

        :raises RuntimeError: when neither symlinks nor copies are supported

        """
        super().add_parser_arguments(parser, interpreter, meta, app_data)
        parser.add_argument(
            "--system-site-packages",
            default=False,
            action="store_true",
            dest="system_site",
            help="give the virtual environment access to the system site-packages dir",
        )
        if not meta.can_symlink and not meta.can_copy:
            errors = []
            if meta.symlink_error:
                errors.append(f"symlink: {meta.symlink_error}")
            if meta.copy_error:
                errors.append(f"copy: {meta.copy_error}")
            msg = f"neither symlink or copy method supported: {', '.join(errors)}"
            raise RuntimeError(msg)
        group = parser.add_mutually_exclusive_group()
        if meta.can_symlink:
            group.add_argument(
                "--symlinks",
                default=True,
                action="store_true",
                dest="symlinks",
                help="try to use symlinks rather than copies, when symlinks are not the default for the platform",
            )
        if meta.can_copy:
            group.add_argument(
                "--copies",
                "--always-copy",
                default=not meta.can_symlink,
                action="store_true",
                dest="copies",
                help="try to use copies rather than symlinks, even when symlinks are the default for the platform",
            )

    def create(self) -> None:
        """Create the environment by installing the patch that guards the import hook."""
        self.install_patch()

    def install_patch(self) -> None:
        """Write the distutils guard files into the purelib folder, only on interpreters older than Python 3.10."""
        # Python 3.10+ ignores the distutils install config keys this patch guards against (pip does so by default,
        # setuptools and CPython's vendored distutils drop them too), so the runtime import hook only earns its
        # startup cost on 3.9. See https://github.com/pypa/virtualenv/issues/3181.
        if self.interpreter.version_info >= (3, 10):
            return
        if text := self.env_patch_text():
            pth = self.purelib / "_virtualenv.pth"
            LOGGER.debug("create virtualenv import hook file %s", pth)
            write_file(pth, b"import _virtualenv")
            dest_path = self.purelib / "_virtualenv.py"
            LOGGER.debug("create %s", dest_path)
            write_file(dest_path, text.encode("utf-8"))

    def env_patch_text(self) -> str:
        """Patch the distutils package to not be derailed by its configuration files.

        :returns: the source text of the patch module

        """
        with self.app_data.ensure_extracted(Path(__file__).parent / "_virtualenv.py") as resolved_path:
            return resolved_path.read_text(encoding="utf-8")

    def _args(self) -> list[tuple[str, str | bool]]:
        return [*super()._args(), ("global", self.enable_system_site_package)]

    def set_pyenv_cfg(self) -> None:
        """Record whether the system site-packages are visible to the environment."""
        super().set_pyenv_cfg()
        self.pyenv_cfg["include-system-site-packages"] = "true" if self.enable_system_site_package else "false"


__all__ = [
    "ViaGlobalRefApi",
    "ViaGlobalRefMeta",
]
