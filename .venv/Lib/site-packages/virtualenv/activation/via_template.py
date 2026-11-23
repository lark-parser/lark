from __future__ import annotations

__lazy_modules__ = [
    "importlib.resources",
    "re",
    "shlex",
    "virtualenv.util.path",
]

import os
import re
import shlex
import sys
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Final

from virtualenv.util.path import write_file

from .activator import Activator

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator
    from pathlib import Path

    from virtualenv.create.creator import Creator

if sys.version_info >= (3, 10):
    from importlib.resources import files

    def read_binary(module_name: str, filename: str) -> bytes:
        return (files(module_name) / filename).read_bytes()

else:
    from importlib.resources import read_binary


class ViaTemplateActivator(Activator, ABC):
    """Base for activators that fill placeholders in a template file and write the result beside the interpreter."""

    def generate(self, creator: Creator) -> list[Path]:
        """Write the activation scripts into the bin folder and set the prompt in ``pyvenv.cfg`` when one was given.

        :param creator: the creator of the environment

        :returns: the paths of the generated scripts

        """
        dest_folder = creator.bin_dir
        generated = self._generate(self.replacements(creator, dest_folder), self.templates(), dest_folder, creator)
        if self.flag_prompt is not None:
            creator.pyenv_cfg["prompt"] = self.flag_prompt
        return generated

    def _generate(
        self, replacements: dict[str, str], templates: Iterable[str], to_folder: Path, creator: Creator
    ) -> list[Path]:
        generated: Final[list[Path]] = []
        for template in templates:
            text: Final[str] = self.instantiate_template(replacements, template, creator)
            dest: Final[Path] = to_folder / self.as_name(template)
            # PowerShell assumes Windows 1252 when the UTF-8 BOM is absent.
            encoding: Final[str] = "utf-8-sig" if str(template).endswith(".ps1") else "utf-8"
            # csh literals keep individual non-ASCII bytes undecoded across shell locale changes.
            write_file(dest, text.encode(encoding, "surrogateescape" if str(template).endswith(".csh") else "strict"))
            generated.append(dest)
        return generated

    def instantiate_template(self, replacements: dict[str, str], template: str, creator: Creator) -> str:
        """Fill the placeholders in a template file with the substituted values.

        :param replacements: the raw placeholder values
        :param template: the name of the template file
        :param creator: the creator of the environment

        :returns: the template text with every placeholder replaced

        """
        # read content as binary to avoid platform specific line normalization (\n -> \r\n)
        # templates ship beside the activator's package, which is the class's own module when it is a package
        package: Final[str] = (
            self.__module__ if hasattr(sys.modules[self.__module__], "__path__") else self.__module__.rpartition(".")[0]
        )
        text = read_binary(package, template).decode("utf-8", errors="strict")
        substitutions = self.substitutions(replacements, creator)
        # one pass over the template, so a placeholder name inside an already quoted value (a path component named
        # __VIRTUAL_NAME__) stays data instead of being rewritten by a later key from inside the finished literal
        pattern = re.compile("|".join(re.escape(key) for key in sorted(substitutions, key=len, reverse=True)))
        return pattern.sub(lambda match: substitutions[match.group()], text)

    def substitutions(self, replacements: dict[str, str], creator: Creator) -> dict[str, str]:
        """Map each placeholder to the final text that replaces it in the template.

        :param replacements: the raw placeholder values
        :param creator: the creator of the environment

        :returns: the placeholder to substituted text mapping

        """
        return {key: self.quote(self._repr_unicode(creator, value)) for key, value in replacements.items()}

    @staticmethod
    def quote(string: str) -> str:
        """Quote strings in the activation script.

        :param string: the string to quote

        :returns: quoted string that works in the activation script

        """
        return shlex.quote(string)

    @staticmethod
    # the quoting hook shares its signature with the other quoters, creator is unused
    def _repr_unicode(creator: Creator, value: str) -> str:  # ruff:ignore[unused-static-method-argument]
        return value  # by default, we just let it be unicode

    def as_name(self, template: str) -> str:
        """The file name of the generated script, which is the template name by default.

        :param template: the name of the template file

        :returns: the name of the generated script

        """
        return template

    # the replacement hook signature, subclasses use these arguments
    def replacements(self, creator: Creator, dest_folder: Path) -> dict[str, str]:  # ruff:ignore[unused-method-argument]
        """The raw placeholder values shared by the activation scripts.

        :param creator: the creator of the environment
        :param dest_folder: the folder the scripts are written into

        :returns: the placeholder names mapped to their values

        """
        return {
            "__VIRTUAL_PROMPT__": "" if self.flag_prompt is None else self.flag_prompt,
            "__VIRTUAL_ENV__": str(creator.dest),
            "__VIRTUAL_NAME__": creator.env_name,
            "__BIN_NAME__": str(creator.bin_dir.relative_to(creator.dest)),
            "__PATH_SEP__": os.pathsep,
            "__TCL_LIBRARY__": self._library_path(creator, "tcl_lib", b"TCL_LIBRARY"),
            "__TK_LIBRARY__": self._library_path(creator, "tk_lib", b"TK_LIBRARY"),
        }

    @staticmethod
    def _library_path(creator: Creator, attribute: str, environment_name: bytes) -> str:
        path = getattr(creator.interpreter, attribute, None) or ""
        if os.name == "nt" or path.isascii():
            return path
        # Tcl may decode the raw environment path with a different codec than the activation script uses.
        source = os.environb.get(environment_name)
        try:
            encoded = path.encode("utf-8")
            if source == encoded:
                return path
            if source is None and environment_name == b"TK_LIBRARY":
                tcl = creator.interpreter.tcl_lib
                if tcl and os.environb.get(b"TCL_LIBRARY") == tcl.encode("utf-8") and os.fsencode(path) == encoded:
                    return path
        except UnicodeEncodeError:
            return ""
        return ""

    @abstractmethod
    def templates(self) -> Iterator[str]:
        """The template file names to instantiate.

        :returns: the template file names

        """
        raise NotImplementedError


__all__ = [
    "ViaTemplateActivator",
]
