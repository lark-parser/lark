"""The Apple Framework builds require their own customization."""

from __future__ import annotations

__lazy_modules__ = [
    "pathlib",
    "struct",
    "subprocess",
    "textwrap",
    "virtualenv.create.via_global_ref.builtin.ref",
    "virtualenv.create.via_global_ref.builtin.via_global_self_do",
]

import logging
import os
import struct
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from textwrap import dedent
from typing import TYPE_CHECKING, Final

from virtualenv.create.via_global_ref.builtin.ref import (
    ExePathRefToDest,
    PathRefToDest,
    RefMust,
)
from virtualenv.create.via_global_ref.builtin.via_global_self_do import BuiltinViaGlobalRefMeta

from .common import CPython, CPythonPosix, is_mac_os_framework, is_macos_brew
from .cpython3 import CPython3

if TYPE_CHECKING:
    from collections.abc import Callable, Generator
    from io import BufferedRandom

    from python_discovery import PythonInfo

    from virtualenv.create.via_global_ref.builtin.ref import PathRef

LOGGER: Final[logging.Logger] = logging.getLogger(__name__)  # simplint: ignore[module-variable-prefix]  # existing name


class CPythonmacOsFramework(CPython, ABC):
    """CPython built as a macOS framework, which needs its Mach-O image paths rewritten."""

    @classmethod
    def can_describe(cls, interpreter: PythonInfo) -> bool:
        """Accept interpreters that are macOS framework builds and that the base describer also accepts.

        :param interpreter: the host interpreter to check

        :returns: ``True`` if this creator can describe the interpreter

        """
        return is_mac_os_framework(interpreter) and super().can_describe(interpreter)

    def create(self) -> None:
        """Create the environment, then rewrite and ad-hoc re-sign the copied executables.

        Re-signing failures are logged as warnings and do not stop the creation.

        """
        super().create()

        target = self.desired_mach_o_image_path()
        current = self.current_mach_o_image_path()
        for src in self._sources:
            if isinstance(src, ExePathRefToDest) and (src.must == RefMust.COPY or not self.symlinks):
                exes = [self.bin_dir / src.base]
                if not self.symlinks:
                    exes.extend(self.bin_dir / a for a in src.aliases)
                for exe in exes:
                    fix_mach_o(str(exe), current, target, self.interpreter.max_size)
                    try:
                        # codesign ships with macOS and is meant to be found on PATH
                        subprocess.check_call(["codesign", "--force", "--sign", "-", str(exe)])  # ruff:ignore[start-process-with-partial-path]
                    except (OSError, subprocess.CalledProcessError) as error:
                        LOGGER.warning("Could not ad-hoc re-sign %s: %s", exe, error)

    @abstractmethod
    def desired_mach_o_image_path(self) -> str:
        """The Mach-O image path the copied executables should reference.

        :returns: the image path inside the environment

        """
        raise NotImplementedError

    @abstractmethod
    def current_mach_o_image_path(self) -> str:
        """The Mach-O image path the copied executables currently reference.

        :returns: the image path the executables were linked against

        """
        raise NotImplementedError

    @classmethod
    def _executables(cls, interpreter: PythonInfo) -> Generator[tuple[Path, list[str], str, str]]:
        for _, targets, must, when in super()._executables(interpreter):
            # Make sure we use the embedded interpreter inside the framework, even if sys.executable points to the
            # stub executable in ${sys.prefix}/bin.
            # See http://groups.google.com/group/python-virtualenv/browse_thread/thread/17cab2f85da75951
            # prefix is typed str | None, and Path needs a str
            fixed_host_exe = Path(interpreter.prefix) / "Resources" / "Python.app" / "Contents" / "MacOS" / "Python"  # ty: ignore[invalid-argument-type]
            yield fixed_host_exe, targets, must, when


def fix_mach_o(  # simplint: ignore[unexported-public-name]  # existing name
    exe: str, current: str, new: str, max_size: int
) -> None:
    """Rewrite the Mach-O library reference of an executable, falling back to ``install_name_tool``.

    :param exe: the executable to rewrite
    :param current: the library reference to replace
    :param new: the library reference to use instead
    :param max_size: the largest Mach-O header size the builtin rewrite handles

    """  # simplint: ignore[function-docstring]  # existing docs
    try:
        LOGGER.debug("change Mach-O for %s from %s to %s", exe, current, new)
        _builtin_change_mach_o(max_size)(exe, current, new)
    # install_name_tool is the fallback for any failure of the builtin rewrite
    except Exception as error:  # ruff:ignore[blind-except]
        LOGGER.warning("Could not call _builtin_change_mac_o: %s. Trying to call install_name_tool instead.", error)
        try:
            subprocess.check_call(["install_name_tool", "-change", current, new, exe])  # ruff:ignore[start-process-with-partial-path]  # the macOS developer tools put it on PATH
        except Exception:
            logging.fatal("Could not call install_name_tool -- you must have Apple's development tools installed")
            raise


# the nested helpers share the file view, so the parser stays one function
def _builtin_change_mach_o(maxint: int) -> Callable[[str, str, str], None]:  # ruff:ignore[complex-structure]
    # the constant keeps its Mach-O header name
    MH_MAGIC = 0xFEEDFACE  # ruff:ignore[non-lowercase-variable-in-function]
    # the constant keeps its Mach-O header name
    MH_CIGAM = 0xCEFAEDFE  # ruff:ignore[non-lowercase-variable-in-function]
    # the constant keeps its Mach-O header name
    MH_MAGIC_64 = 0xFEEDFACF  # ruff:ignore[non-lowercase-variable-in-function]
    # the constant keeps its Mach-O header name
    MH_CIGAM_64 = 0xCFFAEDFE  # ruff:ignore[non-lowercase-variable-in-function]
    # the constant keeps its Mach-O header name
    FAT_MAGIC = 0xCAFEBABE  # ruff:ignore[non-lowercase-variable-in-function]
    # the struct byte-order marker is named for what it selects
    BIG_ENDIAN = ">"  # ruff:ignore[non-lowercase-variable-in-function]
    # the struct byte-order marker is named for what it selects
    LITTLE_ENDIAN = "<"  # ruff:ignore[non-lowercase-variable-in-function]
    LC_LOAD_DYLIB = 0xC  # ruff:ignore[non-lowercase-variable-in-function]  # the constant keeps its Mach-O header name

    # adapted from macholib, which the Mach-O rewriting follows
    class FileView:
        def __init__(self, file_obj: FileView | BufferedRandom, start: int = 0, size: int = maxint) -> None:
            if isinstance(file_obj, FileView):
                # unwraps a nested FileView, which holds the underlying file object
                self._file_obj = file_obj._file_obj  # ruff:ignore[private-member-access]
            else:
                self._file_obj = file_obj
            self._start = start
            self._end = start + size
            self._pos = 0

        def __repr__(self) -> str:
            return f"<fileview [{self._start:d}, {self._end:d}] {self._file_obj!r}>"

        def tell(self) -> int:
            return self._pos

        def seek(self, offset: int, whence: int = 0) -> None:
            seek_to = offset
            if whence == os.SEEK_SET:
                seek_to += self._start
            elif whence == os.SEEK_CUR:
                seek_to += self._start + self._pos
            elif whence == os.SEEK_END:
                seek_to += self._end
            else:
                msg = f"Invalid whence argument to seek: {whence!r}"
                raise OSError(msg)
            self._checkwindow(seek_to, "seek")
            self._file_obj.seek(seek_to)
            self._pos = seek_to - self._start

        def _checkwindow(self, seek_to: int, op: str) -> None:
            if not (self._start <= seek_to <= self._end):
                msg = f"{op} to offset {seek_to:d} is outside window [{self._start:d}, {self._end:d}]"
                raise OSError(msg)

        def write(self, content: bytes) -> None:
            here = self._start + self._pos
            self._checkwindow(here, "write")
            self._checkwindow(here + len(content), "write")
            self._file_obj.seek(here, os.SEEK_SET)
            self._file_obj.write(content)
            self._pos += len(content)

        def read(self, size: int = maxint) -> bytes:
            assert size >= 0  # ruff:ignore[assert]  # a negative size is a parser bug, so fail fast
            here = self._start + self._pos
            self._checkwindow(here, "read")
            size = min(size, self._end - here)
            self._file_obj.seek(here, os.SEEK_SET)
            read_bytes = self._file_obj.read(size)
            self._pos += len(read_bytes)
            return read_bytes

    def read_data(file: FileView, endian: str, num: int = 1) -> int | tuple[int, ...]:
        res = struct.unpack(endian + "L" * num, file.read(num * 4))
        if len(res) == 1:
            return res[0]
        return res

    # the nested parser helpers close over the file view, so they stay in one function
    def mach_o_change(at_path: str, what: str, value: str) -> None:  # ruff:ignore[complex-structure]

        def do_macho(file: FileView, bits: int, endian: str) -> None:
            # Read Mach-O header (the magic number is assumed read by the caller)
            # read_data returns a tuple for six values, but ty types it as int | tuple
            _cpu_type, _cpu_sub_type, _file_type, n_commands, _size_of_commands, _flags = read_data(file, endian, 6)  # ty: ignore[not-iterable]
            # 64-bits header has one more field.
            if bits == 64:  # ruff:ignore[magic-value-comparison]
                read_data(file, endian)
            # The header is followed by n commands
            for _ in range(n_commands):
                where = file.tell()
                # Read command header
                # read_data returns a tuple for two values, but ty types it as int | tuple
                cmd, cmd_size = read_data(file, endian, 2)  # ty: ignore[not-iterable]
                if cmd == LC_LOAD_DYLIB:
                    # The first data field in LC_LOAD_DYLIB commands is the offset of the name, starting from the
                    # beginning of the  command.
                    name_offset = read_data(file, endian)
                    # read_data with one value returns an int, but ty types it as int | tuple
                    file.seek(where + name_offset, os.SEEK_SET)  # ty: ignore[unsupported-operator]
                    # Read the NUL terminated string
                    load = file.read(cmd_size - name_offset).decode()  # ty: ignore[unsupported-operator]
                    load = load[: load.index("\0")]
                    # If the string is what is being replaced, overwrite it.
                    if load == what:
                        # read_data with one value returns an int, but ty types it as int | tuple
                        file.seek(where + name_offset, os.SEEK_SET)  # ty: ignore[unsupported-operator]
                        file.write(value.encode() + b"\0")
                # Seek to the next command
                file.seek(where + cmd_size, os.SEEK_SET)

        def do_file(file: FileView | BufferedRandom, offset: int = 0, size: int = maxint) -> None:
            file = FileView(file, offset, size)
            # Read magic number
            if (magic := read_data(file, BIG_ENDIAN)) == FAT_MAGIC:
                # Fat binaries contain nfat_arch Mach-O binaries
                n_fat_arch = read_data(file, BIG_ENDIAN)
                # read_data with one value returns an int, but ty types it as int | tuple
                for _ in range(n_fat_arch):  # ty: ignore[invalid-argument-type]
                    # Read arch header
                    # read_data returns a tuple for five values, but ty types it as int | tuple
                    _cpu_type, _cpu_sub_type, offset, size, _align = read_data(file, BIG_ENDIAN, 5)  # ty: ignore[not-iterable]
                    do_file(file, offset, size)
            elif magic == MH_MAGIC:
                do_macho(file, 32, BIG_ENDIAN)
            elif magic == MH_CIGAM:
                do_macho(file, 32, LITTLE_ENDIAN)
            elif magic == MH_MAGIC_64:
                do_macho(file, 64, BIG_ENDIAN)
            elif magic == MH_CIGAM_64:
                do_macho(file, 64, LITTLE_ENDIAN)

        # the in-place rewrite must not grow the name, so a longer value is a bug
        assert len(what) >= len(value)  # ruff:ignore[assert]

        with open(at_path, "r+b") as file_handler:
            do_file(file_handler)

    return mach_o_change


class CPython3macOsFramework(CPythonmacOsFramework, CPython3, CPythonPosix):
    """CPython 3 built as a macOS framework."""

    @property
    def reload_code(self) -> str:
        """Source of the ``reload_code`` snippet, which turns off the framework site package behavior."""
        # reload_code is defined on a base that ty does not resolve through this super()
        result = super().reload_code  # ty: ignore[missing-attribute]
        return dedent(
            f"""
        # the bundled site.py always adds the global site package if we're on python framework build, escape this
        import sys
        before = sys._framework
        try:
            sys._framework = None
            {result}
        finally:
            sys._framework = before
        """,
        )

    def current_mach_o_image_path(self) -> str:
        """The Mach-O image path the copied executables currently reference, relative to the bundle.

        :returns: the image path the executables were linked against

        """
        return "@executable_path/../../../../Python3"

    def desired_mach_o_image_path(self) -> str:
        """The Mach-O image path the copied executables should reference, inside the environment.

        :returns: the image path inside the environment

        """
        return "@executable_path/../.Python"

    @classmethod
    # yields PathRef, which the base's Generator[ExePathRefToDest] does not allow
    def sources(cls, interpreter: PythonInfo) -> Generator[PathRef]:  # ty: ignore[incompatible-method-override]
        """Yield the framework executables, plus a symlink to the host framework image.

        :param interpreter: the host interpreter to take the files from

        :yields: the references to the host files

        """
        yield from super().sources(interpreter)

        # add a symlink to the host python image
        # prefix is typed str | None, and Path needs a str
        exe = Path(interpreter.prefix) / "Python3"  # ty: ignore[invalid-argument-type]
        yield PathRefToDest(exe, dest=lambda self, _: self.dest / ".Python", must=RefMust.SYMLINK)


class CPython3macOsBrew(CPython3, CPythonPosix):
    """CPython 3 installed by Homebrew, which is created like a POSIX CPython."""

    @classmethod
    def can_describe(cls, interpreter: PythonInfo) -> bool:
        """Accept interpreters installed by Homebrew, which the base describer also accepts.

        :param interpreter: the host interpreter to check

        :returns: ``True`` if this creator can describe the interpreter

        """
        return is_macos_brew(interpreter) and super().can_describe(interpreter)

    @classmethod
    # setup_meta takes the interpreter from the base signature, this meta does not use it
    def setup_meta(cls, interpreter: PythonInfo) -> BuiltinViaGlobalRefMeta:  # ruff:ignore[unused-class-method-argument]
        """Return the metadata for a Homebrew interpreter, which does not depend on the interpreter.

        :param interpreter: the host interpreter, unused

        :returns: a new metadata object

        """
        meta = BuiltinViaGlobalRefMeta()
        meta.copy_error = "Brew disables copy creation: https://github.com/Homebrew/homebrew-core/issues/138159"
        return meta


__all__ = [
    "CPython3macOsBrew",
    "CPython3macOsFramework",
    "CPythonmacOsFramework",
]
