# simplint: ignore[flattened-package]  # ruff: ignore[commented-out-code]  # keep the existing private path
"""Concrete Python interpreter information, collected in-process or via subprocess interrogation."""

from __future__ import annotations

import copy
import json
import logging
import os
import platform
import sys
from collections import OrderedDict
from itertools import product
from os.path import normcase, realpath
from string import Formatter, digits
from typing import TYPE_CHECKING, ClassVar, Final, NamedTuple, TypedDict

from ._py_info_collect import PythonInfoCollector

if TYPE_CHECKING:
    from collections.abc import Generator, Mapping
    from typing import Union

    from ._cache import PyInfoCache
    from ._py_spec import PythonSpec

    InfoValue = Union[str, int, bool, None, "tuple[int | str, ...]", "list[str]", "dict[str, str | int | None]"]


_LOGGER: Final[logging.Logger] = logging.getLogger(__name__)


def _get_path_extensions() -> list[str]:
    return list(OrderedDict.fromkeys(["", *os.environ.get("PATHEXT", "").lower().split(os.pathsep)]))


EXTENSIONS: Final[list[str]] = _get_path_extensions()


class PythonInfo:  # ruff:ignore[too-many-public-methods] public query API
    """
    Contains information for a Python interpreter.

    :ivar platform: the platform name, as reported by ``sys.platform``.
    :ivar implementation: the implementation name, such as ``CPython``.
    :ivar pypy_version_info: the PyPy version tuple, empty for other implementations.
    :ivar version_info: the interpreter version as a named tuple.
    :ivar architecture: the pointer width in bits, ``32`` or ``64``.
    :ivar sysconfig_platform: the platform string from :mod:`sysconfig`, or ``None``.
    :ivar version_nodot: the ``major.minor`` version without the dot.
    :ivar version: the full version string from ``sys.version``.
    :ivar os: the operating system name, as reported by ``os.name``.
    :ivar free_threaded: whether the interpreter was built free-threaded.
    :ivar debug_build: whether the interpreter was built with ``Py_DEBUG``.

    :ivar marker_environment: the PEP 508 marker environment of the interpreter.

    :ivar prefix: the ``sys.prefix`` of the interpreter.
    :ivar base_prefix: the ``sys.base_prefix`` of the interpreter.
    :ivar real_prefix: the ``sys.real_prefix`` set by legacy virtualenv, or ``None``.
    :ivar base_exec_prefix: the ``sys.base_exec_prefix`` of the interpreter.
    :ivar exec_prefix: the ``sys.exec_prefix`` of the interpreter.
    :ivar executable: the ``sys.executable`` of the interpreter.
    :ivar original_executable: the absolute path to the executable, without resolving symlinks.
    :ivar system_executable: the system interpreter behind any virtualenv, or ``None``.
    :ivar has_venv: whether the :mod:`venv` module can be imported.

    :ivar path: the ``sys.path`` of the interpreter.
    :ivar file_system_encoding: the filesystem encoding, from ``sys.getfilesystemencoding()``.
    :ivar stdout_encoding: the encoding of ``sys.stdout``, or ``None``.

    :ivar sysconfig_scheme: the installation scheme behind ``sysconfig_paths``, or ``None``.
    :ivar sysconfig_paths: the installation paths, keyed by :mod:`sysconfig` path name.

    :ivar distutils_install: the distutils installation directories, empty when sysconfig supplies them.
    :ivar sysconfig: the :mod:`sysconfig` build metadata, such as the makefile filename.
    :ivar sysconfig_vars: the :mod:`sysconfig` config variables queried for this interpreter.
    :ivar tcl_lib: the Tcl library path, or ``None``.
    :ivar tk_lib: the Tk library path, or ``None``.
    :ivar system_stdlib: the standard library path of the system interpreter.
    :ivar system_stdlib_platform: the platform standard library path of the system interpreter.
    :ivar max_size: the ``sys.maxsize`` of the interpreter.
    """

    platform: str
    implementation: str
    pypy_version_info: tuple[int, ...]
    version_info: VersionInfo
    architecture: int
    sysconfig_platform: str | None
    version_nodot: str | None
    version: str
    os: str
    free_threaded: bool
    debug_build: bool
    marker_environment: MarkerEnvironment
    prefix: str | None
    base_prefix: str | None
    real_prefix: str | None
    base_exec_prefix: str | None
    exec_prefix: str | None
    executable: str
    original_executable: str
    system_executable: str | None
    has_venv: bool
    path: list[str]
    file_system_encoding: str
    stdout_encoding: str | None
    sysconfig_scheme: str | None
    sysconfig_paths: dict[str, str]
    distutils_install: dict[str, str]
    sysconfig: dict[str, str | None]
    sysconfig_vars: dict[str, str | int | None]
    tcl_lib: str | None
    tk_lib: str | None
    system_stdlib: str
    system_stdlib_platform: str
    max_size: int

    _current_system = None

    _current = None

    _cache_exe_discovery: ClassVar[dict[tuple[str, bool, VersionInfo], PythonInfo]] = {}

    def __init__(self) -> None:
        self.__dict__.update(self.from_dict(PythonInfoCollector().to_dict()).__dict__)

    @classmethod
    def from_dict(cls, data: dict[str, InfoValue]) -> PythonInfo:
        """
        Reconstruct a :class:`PythonInfo` from a plain dictionary.

        :param data: dictionary produced by :meth:`to_dict`.
        :returns: the interpreter information rebuilt from *data*.
        :raises ValueError: if *data* lacks an annotated field.
        """
        if missing := PythonInfo.__annotations__.keys() - data.keys() - {"_cache_exe_discovery", "pypy_version_info"}:
            msg = f"missing interpreter information: {', '.join(sorted(missing))}"
            raise ValueError(msg)
        data["version_info"] = VersionInfo(**data["version_info"])  # restore this to a named tuple structure
        result = cls.__new__(cls)  # skip __init__, data replaces the full state
        result.__dict__ = data.copy()
        return result

    @classmethod
    def current(cls, cache: PyInfoCache | None = None) -> PythonInfo:
        """
        Locate the current host interpreter information.

        :param cache: interpreter metadata cache; when ``None`` results are not cached.
        :returns: the information about the running interpreter.
        :raises RuntimeError: if the running interpreter cannot be queried.
        """
        if cls._current is None:
            result = cls.from_exe(sys.executable, cache, raise_on_error=True, resolve_to_host=False)
            if result is None:
                msg = "failed to query current Python interpreter"
                raise RuntimeError(msg)
            cls._current = result
        return cls._current

    @classmethod
    def from_exe(  # ruff:ignore[too-many-arguments] each argument is a separate probe input
        cls,
        exe: str,
        cache: PyInfoCache | None = None,
        *,
        raise_on_error: bool = True,
        ignore_cache: bool = False,
        resolve_to_host: bool = True,
        env: Mapping[str, str] | None = None,
    ) -> PythonInfo | None:
        """
        Get the python information for a given executable path.

        :param exe: path to the Python executable.
        :param cache: interpreter metadata cache; when ``None`` results are not cached.
        :param raise_on_error: raise on failure instead of returning ``None``.
        :param ignore_cache: bypass the cache and re-query the interpreter.
        :param resolve_to_host: resolve through virtualenv layers to the system interpreter.
        :param env: environment mapping; defaults to :data:`os.environ`.
        :returns: the interpreter information, or ``None`` when it cannot be queried.
        """
        return cls._from_exe_with_args(
            exe,
            cache,
            executable_args=None,
            raise_on_error=raise_on_error,
            ignore_cache=ignore_cache,
            resolve_to_host=resolve_to_host,
            env=env,
        )

    @classmethod
    def _from_exe_with_args(  # ruff:ignore[too-many-arguments] distinct probe inputs
        cls,
        exe: str,
        cache: PyInfoCache | None = None,
        *,
        executable_args: str | None,
        raise_on_error: bool = True,
        ignore_cache: bool = False,
        resolve_to_host: bool = True,
        env: Mapping[str, str] | None = None,
    ) -> PythonInfo | None:
        from ._cached_py_info import from_exe  # ruff:ignore[import-outside-top-level] deferred import avoids a cycle

        env = os.environ if env is None else env
        proposed = from_exe(
            cls,
            cache,
            exe,
            env=env,
            raise_on_error=raise_on_error,
            ignore_cache=ignore_cache,
            executable_args=executable_args,
        )

        if isinstance(proposed, PythonInfo) and resolve_to_host:
            try:
                proposed = proposed.resolve_to_system(cache, proposed, env=env)
            except Exception as exception:
                if raise_on_error:
                    raise
                _LOGGER.info("ignore %s due cannot resolve system due to %r", proposed.original_executable, exception)
                proposed = None
        return proposed

    @classmethod
    def current_system(cls, cache: PyInfoCache | None = None) -> PythonInfo:
        """
        Locate the current system interpreter information, resolving through any virtualenv layers.

        :param cache: interpreter metadata cache; when ``None`` results are not cached.
        :returns: the system interpreter behind any virtualenv layers.
        :raises RuntimeError: if the system interpreter cannot be queried.
        """
        if cls._current_system is None:
            result = cls.from_exe(sys.executable, cache, raise_on_error=True, resolve_to_host=True)
            if result is None:
                msg = "failed to query current system Python interpreter"
                raise RuntimeError(msg)
            cls._current_system = result
        return cls._current_system

    @classmethod
    def from_json(cls, payload: str) -> PythonInfo:
        """
        Deserialize interpreter information from a JSON string.

        :param payload: JSON produced by :meth:`to_json`.
        :returns: the interpreter information decoded from *payload*.
        """
        return cls.from_dict(json.loads(payload).copy())

    @classmethod
    def resolve_to_system(
        cls, cache: PyInfoCache | None, target: PythonInfo, *, env: Mapping[str, str] | None = None
    ) -> PythonInfo:
        """
        Walk virtualenv/venv prefix chains to find the underlying system interpreter.

        :param cache: interpreter metadata cache; when ``None`` results are not cached.
        :param target: the interpreter to resolve.
        :param env: environment mapping; defaults to :data:`os.environ`.
        :returns: the system interpreter that *target* resolves to.
        :raises RuntimeError: if the prefixes form a cycle.
        """
        start_executable = target.executable
        prefixes = OrderedDict()
        while target.system_executable is None:
            prefix = target.real_prefix or target.base_prefix or target.prefix
            prefix_key = normcase(realpath(prefix))
            if prefix_key in prefixes:
                if len(prefixes) == 1:
                    _LOGGER.info("%r links back to itself via prefixes", target)
                    target.system_executable = target.executable
                    break
                for at, (prefix_path, prefix_info) in enumerate(prefixes.items(), start=1):
                    _LOGGER.error("%d: prefix=%s, info=%r", at, prefix_path, prefix_info)
                _LOGGER.error("%d: prefix=%s, info=%r", len(prefixes) + 1, prefix, target)
                msg = "prefixes are causing a circle {}".format("|".join(prefixes.keys()))
                raise RuntimeError(msg)
            prefixes[prefix_key] = target
            target = target.discover_exe(cache, prefix=prefix, exact=False, env=env)
        if (
            target.executable != target.system_executable
            and (resolved := cls.from_exe(target.system_executable, cache, env=env)) is not None
        ):
            target = resolved
        if target.executable != start_executable:
            # the cache hands every lookup of this base the same object, so point a copy at the start executable
            target = copy.copy(target)
            target.executable = start_executable
        return target

    def __repr__(self) -> str:
        return "{}({!r})".format(
            self.__class__.__name__,
            {k: v for k, v in self.__dict__.items() if not k.startswith("_")},
        )

    def __str__(self) -> str:
        return "{}({})".format(
            self.__class__.__name__,
            ", ".join(
                f"{k}={v}"
                for k, v in (
                    ("spec", self.spec),
                    (
                        "system"
                        if self.system_executable is not None and self.system_executable != self.executable
                        else None,
                        self.system_executable,
                    ),
                    (
                        "original"
                        if self.original_executable not in {self.system_executable, self.executable}
                        else None,
                        self.original_executable,
                    ),
                    ("exe", self.executable),
                    ("platform", self.platform),
                    ("version", repr(self.version)),
                    ("encoding_fs_io", f"{self.file_system_encoding}-{self.stdout_encoding}"),
                )
                if k is not None
            ),
        )

    @property
    def spec(self) -> str:
        """A specification string identifying this interpreter (e.g. ``CPython3.13.2-64-arm64``)."""
        return "{}{}{}{}-{}-{}".format(
            self.implementation,
            ".".join(str(i) for i in self.version_info),
            "t" if self.free_threaded else "",
            "d" if self.debug_build else "",
            self.architecture,
            self.machine,
        )

    @property
    def machine(self) -> str:
        """The instruction set architecture (ISA) derived from :func:`sysconfig.get_platform`."""
        plat = self.sysconfig_platform
        if plat is None:
            return "unknown"
        if plat == "win32":
            return "x86"
        isa = plat.rsplit("-", 1)[-1]
        if isa == "universal2":
            isa = platform.machine().lower()
        return normalize_isa(isa)

    @property
    def version_str(self) -> str:
        """The full version as ``major.minor.micro`` string (e.g. ``3.13.2``)."""
        return ".".join(str(i) for i in self.version_info[0:3])

    @property
    def version_release_str(self) -> str:
        """The release version as ``major.minor`` string (e.g. ``3.13``)."""
        return ".".join(str(i) for i in self.version_info[0:2])

    @property
    def python_name(self) -> str:
        """The python executable name as ``pythonX.Y`` (e.g. ``python3.13``)."""
        version_info = self.version_info
        return f"python{version_info.major}.{version_info.minor}"

    @property
    def is_old_virtualenv(self) -> bool:
        """``True`` if this interpreter runs inside an old-style virtualenv (has ``real_prefix``)."""
        return self.real_prefix is not None

    @property
    def is_venv(self) -> bool:
        """``True`` if this interpreter runs inside a PEP 405 venv (has ``base_prefix``)."""
        return self.base_prefix is not None

    @property
    def system_include(self) -> str:
        """The path to the system include directory for C headers."""
        path = self.sysconfig_path(
            "include",
            {
                k: (self.system_prefix if isinstance(v, str) and v.startswith(self.prefix) else v)
                for k, v in self.sysconfig_vars.items()
            },
        )
        # An empty headers path would make the fallback resolve to the existing prefix.
        if not os.path.exists(path) and (headers := os.path.dirname(self.install_path("headers"))):
            fallback = os.path.join(self.prefix, headers)
            if os.path.exists(fallback):
                path = fallback
        return path

    def sysconfig_path(self, key: str, config_var: dict[str, str | int | None] | None = None, sep: str = os.sep) -> str:
        """
        Return the sysconfig install path for a scheme *key*, optionally substituting config variables.

        :param key: sysconfig path key (e.g. ``"purelib"``, ``"include"``).
        :param config_var: replacement mapping for sysconfig variables; when ``None`` uses the interpreter's own values.
        :param sep: path separator to use in the result.
        :returns: the path, or an empty string if *key* is unknown.
        :raises ValueError: if the sysconfig pattern contains format specifiers.
        """
        pattern = self.sysconfig_paths.get(key)
        if pattern is None:
            return ""
        if any(format_spec for _, _, format_spec, _ in Formatter().parse(pattern)):
            msg = f"sysconfig path {key!r} contains format specifiers"
            raise ValueError(msg)
        if config_var is None:
            config_var = self.sysconfig_vars
        else:
            base = self.sysconfig_vars.copy()
            base.update(config_var)
            config_var = base
        return pattern.format(**config_var).replace("/", sep)

    @property
    def system_prefix(self) -> str:
        """The prefix of the system Python this interpreter is based on."""
        return self.real_prefix or self.base_prefix or self.prefix

    def install_path(self, key: str) -> str:
        """
        Return the relative installation path for a given installation scheme *key*.

        :param key: sysconfig installation scheme key (e.g. ``"scripts"``, ``"purelib"``).
        :returns: the installation path relative to the prefix.
        """
        result = self.distutils_install.get(key)
        if result is None:  # pragma: >=3.11 cover # distutils is empty when "venv" scheme is available
            # set prefixes to empty => result is relative from cwd
            prefixes = self.prefix, self.exec_prefix, self.base_prefix, self.base_exec_prefix
            config_var = {k: "" if v in prefixes else v for k, v in self.sysconfig_vars.items()}
            result = self.sysconfig_path(key, config_var=config_var).lstrip(os.sep)
        return result

    @property
    def system_exec_prefix(self) -> str:
        """The exec prefix of the system Python this interpreter is based on."""
        return self.real_prefix or self.base_exec_prefix or self.exec_prefix

    @property
    def system_exe(self) -> str:
        """
        The executable of the system Python this interpreter is based on.

        :attr:`system_executable` stays ``None`` until :meth:`resolve_to_system` walks the prefix chain, so reading it
        forces every caller to narrow a value discovery has already settled. The fallback here matches what resolution
        itself writes when a prefix links back to its own interpreter.
        """
        return self.system_executable or self.executable

    @classmethod
    def clear_cache(cls, cache: PyInfoCache) -> None:
        """
        Clear all cached interpreter information from *cache*.

        :param cache: the cache store to clear.
        """
        from ._cached_py_info import clear  # ruff:ignore[import-outside-top-level] import cycle

        clear(cache)
        cls._cache_exe_discovery.clear()

    # ruff:ignore[too-many-return-statements] distinct outcomes
    def satisfies(self, spec: PythonSpec, *, impl_must_match: bool) -> bool:
        """
        Check if a given specification can be satisfied by this python interpreter instance.

        :param spec: the specification to check against.
        :param impl_must_match: when ``True``, the implementation name must match exactly.
        :returns: ``True`` if this interpreter satisfies *spec*.
        """
        if spec.path and not self._satisfies_path(spec):
            return False
        if impl_must_match and not self._satisfies_implementation(spec):
            return False
        if spec.architecture is not None and spec.architecture != self.architecture:
            return False
        if spec.machine is not None and spec.machine != self.machine:
            return False
        if spec.free_threaded is not None and spec.free_threaded != self.free_threaded:
            return False
        if spec.debug is not None and spec.debug != self.debug_build:
            return False
        if spec.version_specifier is not None and not self._satisfies_version_specifier(spec):
            return False
        return all(
            req is None or our is None or our == req
            for our, req in zip(self.version_info[0:3], (spec.major, spec.minor, spec.micro))
        )

    def _satisfies_path(self, spec: PythonSpec) -> bool:
        if self.executable == os.path.abspath(spec.path):
            return True
        if spec.is_abs:
            return True
        basename = os.path.basename(self.executable)
        spec_path = spec.path
        if sys.platform == "win32":
            basename, suffix = os.path.splitext(basename)
            spec_path = spec_path[: -len(suffix)] if suffix and spec_path.endswith(suffix) else spec_path
        return basename == spec_path

    def _satisfies_implementation(self, spec: PythonSpec) -> bool:
        return spec.implementation is None or spec.implementation.lower() == self.implementation.lower()

    def _satisfies_version_specifier(self, spec: PythonSpec) -> bool:
        if spec.version_specifier is None:  # pragma: no cover, defensive guard for specs without a version specifier
            return True
        version_info = self.version_info
        for specifier in spec.version_specifier:
            if specifier.version is None:  # a hand-built spec can carry an unparsable version, which matches nothing
                return False
            numeric_version = specifier.version_str
            for prefix in ("rc", "b", "a"):
                if prefix in numeric_version:
                    numeric_version = numeric_version.split(prefix)[0]
                    break
            precision = numeric_version.count(".") + 1
            release = ".".join(str(c) for c in [version_info.major, version_info.minor, version_info.micro][:precision])
            if (
                version_info.releaselevel != "final"
                # ruff:ignore[magic-value-comparison] full version has three parts
                and (precision == 3 or specifier.version.pre_type is not None)
                and (suffix := {"alpha": "a", "beta": "b", "candidate": "rc"}.get(version_info.releaselevel))
            ):
                release = f"{release}{suffix}{version_info.serial}"
            if not specifier.contains(release):
                return False
        return True

    def to_json(self) -> str:
        """
        Serialize this interpreter information to a JSON string.

        :returns: the JSON document.
        """
        return json.dumps(self.to_dict(), indent=2)

    def to_dict(self) -> dict[str, InfoValue]:
        """
        Convert this interpreter information to a plain dictionary.

        :returns: the interpreter information as a dictionary.
        """
        data = {name: None if name == "_creators" else value for name, value in vars(self).items()}
        version_info = data["version_info"]
        data["version_info"] = version_info._asdict() if hasattr(version_info, "_asdict") else version_info
        return data

    def discover_exe(
        self,
        cache: PyInfoCache,
        prefix: str,
        *,
        exact: bool = True,
        env: Mapping[str, str] | None = None,
    ) -> PythonInfo:
        """
        Discover a matching Python executable under a given *prefix* directory.

        :param cache: interpreter metadata cache.
        :param prefix: directory prefix to search under.
        :param exact: when ``True``, require an exact version match.
        :param env: environment mapping; defaults to :data:`os.environ`.
        :returns: the matching interpreter information.
        :raises RuntimeError: if no matching interpreter is found.
        """
        key = prefix, exact, self.version_info
        if key in self._cache_exe_discovery and prefix:
            _LOGGER.debug("discover exe from cache %s - exact %s: %r", prefix, exact, self._cache_exe_discovery[key])
            return self._cache_exe_discovery[key]
        _LOGGER.debug("discover exe for %s in %s", self, prefix)
        possible_names = self._find_possible_exe_names()
        possible_folders = self._find_possible_folders(prefix)
        env = os.environ if env is None else env
        discovered = []
        for folder in possible_folders:
            for name in possible_names:
                info = self._check_exe(cache, folder, name, discovered, env, exact=exact)
                if info is not None:
                    self._cache_exe_discovery[key] = info
                    return info
        if exact is False and discovered:
            info = self._select_most_likely(discovered, self)
            folders = os.pathsep.join(possible_folders)
            self._cache_exe_discovery[key] = info
            _LOGGER.debug("no exact match found, chosen most similar of %s within base folders %s", info, folders)
            return info
        msg = "failed to detect {} in {}".format("|".join(possible_names), os.pathsep.join(possible_folders))
        raise RuntimeError(msg)

    def _find_possible_exe_names(self) -> list[str]:
        name_candidate = OrderedDict()
        mods = ["", "t"] if self.free_threaded else [""]
        # _d (Windows python_d.exe), -dbg (Debian's own name), d (the abiflags form used by
        # upstream/Fedora and also shipped by Debian, so pythonX.Yd / pythonX.Ytd resolve too)
        debug_suffixes = ["_d", "-dbg", "d", ""] if self.debug_build else [""]
        archs = [f"-{self.architecture}", ""]
        for name in self._possible_base():
            for at in (3, 2, 1, 0):
                version = ".".join(str(i) for i in self.version_info[:at])
                for mod, debug, arch, ext in product(mods, debug_suffixes, archs, EXTENSIONS):
                    name_candidate[f"{name}{version}{mod}{debug}{arch}{ext}"] = None
        return list(name_candidate.keys())

    def _possible_base(self) -> Generator[str, None, None]:
        possible_base = OrderedDict()
        possible_base[os.path.splitext(os.path.basename(self.executable))[0].rstrip(digits)] = None
        possible_base[self.implementation] = None
        # python is always the final option as in practice is used by multiple implementation as exe name
        if "python" in possible_base:
            del possible_base["python"]
        possible_base["python"] = None
        for base in possible_base:
            lower = base.lower()
            yield lower
            from ._compat import fs_is_case_sensitive  # ruff:ignore[import-outside-top-level] cold path

            if fs_is_case_sensitive():  # pragma: no branch, the branch depends on the host filesystem
                if base != lower:
                    yield base
                if (upper := base.upper()) != base:
                    yield upper

    def _find_possible_folders(self, inside_folder: str) -> list[str]:
        candidate_folder = OrderedDict()
        executables = OrderedDict()
        executables[os.path.realpath(self.executable)] = None
        executables[self.executable] = None
        executables[os.path.realpath(self.original_executable)] = None
        executables[self.original_executable] = None
        for exe in executables:
            base = os.path.dirname(exe)
            if base.startswith(self.prefix):
                candidate_folder[f"{inside_folder}{base[len(self.prefix) :]}"] = None

        # or at root level
        candidate_folder[inside_folder] = None
        return [i for i in candidate_folder if os.path.exists(i)]

    def _check_exe(  # ruff:ignore[too-many-arguments] each argument is a separate probe input
        self,
        cache: PyInfoCache | None,
        folder: str,
        name: str,
        discovered: list[PythonInfo],
        env: Mapping[str, str],
        *,
        exact: bool,
    ) -> PythonInfo | None:
        exe_path = os.path.join(folder, name)
        if not os.path.exists(exe_path):
            return None
        info = self.from_exe(exe_path, cache, resolve_to_host=False, raise_on_error=False, env=env)
        if info is None:  # ignore if for some reason we can't query
            return None
        for item in ["implementation", "architecture", "machine", "version_info", "free_threaded", "debug_build"]:
            found = getattr(info, item)
            searched = getattr(self, item)
            if found != searched:
                if item == "version_info":
                    found, searched = ".".join(str(i) for i in found), ".".join(str(i) for i in searched)
                executable = info.executable
                _LOGGER.debug("refused interpreter %s because %s differs %s != %s", executable, item, found, searched)
                if exact is False:
                    discovered.append(info)
                break
        else:
            return info
        return None

    @staticmethod
    def _select_most_likely(discovered: list[PythonInfo], target: PythonInfo) -> PythonInfo:
        def sort_by(info: PythonInfo) -> int:
            # we need to setup some priority of traits, this is as follows:
            # implementation, major, minor, architecture, machine, micro, tag, serial
            matches = [
                info.implementation == target.implementation,
                info.version_info.major == target.version_info.major,
                info.version_info.minor == target.version_info.minor,
                info.architecture == target.architecture,
                info.machine == target.machine,
                info.version_info.micro == target.version_info.micro,
                info.version_info.releaselevel == target.version_info.releaselevel,
                info.version_info.serial == target.version_info.serial,
            ]
            return sum((1 << pos if match else 0) for pos, match in enumerate(reversed(matches)))

        sorted_discovered = sorted(discovered, key=sort_by, reverse=True)  # sort by priority in decreasing order
        return sorted_discovered[0]


class VersionInfo(NamedTuple):
    major: int
    minor: int
    micro: int
    releaselevel: str
    serial: int


def normalize_isa(isa: str) -> str:
    """
    Normalize an ISA (instruction set architecture) string to a canonical form.

    Known aliases are mapped (e.g. ``amd64`` → ``x86_64``, ``aarch64`` → ``arm64``).
    Unrecognized values are lowercased and returned as-is.

    :param isa: the architecture string as the platform reports it.
    :returns: the normalized architecture name.
    """
    low = isa.lower()
    return {
        "amd64": "x86_64",
        "aarch64": "arm64",
        "i386": "x86",
        "i486": "x86",
        "i586": "x86",
        "i686": "x86",
        "powerpc": "ppc",
        "powerpc64": "ppc64",
        "powerpc64le": "ppc64le",
        "sparcv9": "sparc64",
    }.get(low, low)


class MarkerEnvironment(TypedDict):
    """
    Environment markers of an interpreter, as defined by PEP 508.

    :ivar implementation_name: the ``implementation_name`` marker.
    :ivar implementation_version: the ``implementation_version`` marker.
    :ivar os_name: the ``os_name`` marker.
    :ivar platform_machine: the ``platform_machine`` marker.
    :ivar platform_release: the ``platform_release`` marker.
    :ivar platform_system: the ``platform_system`` marker.
    :ivar platform_version: the ``platform_version`` marker.
    :ivar python_full_version: the ``python_full_version`` marker.
    :ivar platform_python_implementation: the ``platform_python_implementation`` marker.
    :ivar python_version: the ``python_version`` marker.
    :ivar sys_platform: the ``sys_platform`` marker.
    """

    implementation_name: str
    implementation_version: str
    os_name: str
    platform_machine: str
    platform_release: str
    platform_system: str
    platform_version: str
    python_full_version: str
    platform_python_implementation: str
    python_version: str
    sys_platform: str


KNOWN_ARCHITECTURES: Final[frozenset[str]] = frozenset({
    "arm64",
    "loongarch64",
    "ppc",
    "ppc64",
    "ppc64le",
    "riscv64",
    "s390x",
    "sparc64",
    "x86",
    "x86_64",
})
"""Known CPU architecture (ISA) values after normalization.

.. deprecated::
    Use :func:`normalize_isa` instead, which handles both known and unknown architectures.
"""


__all__ = [
    "KNOWN_ARCHITECTURES",
    "MarkerEnvironment",
    "PythonInfo",
    "VersionInfo",
    "normalize_isa",
]
