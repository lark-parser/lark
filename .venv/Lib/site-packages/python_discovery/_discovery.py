from __future__ import annotations

import logging
import os
import sys
from contextlib import suppress
from dataclasses import dataclass
from itertools import tee
from os.path import basename
from pathlib import Path
from typing import TYPE_CHECKING, Final

from ._compat import fs_path_id
from ._py_info import PythonInfo
from ._py_spec import KNOWN_IMPLEMENTATIONS, PythonSpec
from ._specifier import DC_KW, SimpleSpecifier, SimpleVersion

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Iterable, Iterator, Mapping, Sequence

    from ._cache import PyInfoCache

_LOGGER: Final[logging.Logger] = logging.getLogger(__name__)
IS_WIN: Final[bool] = sys.platform == "win32"


def get_interpreter(
    key: str | Sequence[str],
    try_first_with: Iterable[str] | None = None,
    cache: PyInfoCache | None = None,
    env: Mapping[str, str] | None = None,
    predicate: Callable[[PythonInfo], bool] | None = None,
) -> PythonInfo | None:
    """
    Find a Python interpreter matching *key*.

    Iterates over one or more specification strings and returns the first interpreter that satisfies the spec and passes
    the optional *predicate*.

    :param key: interpreter specification string(s) — an absolute path, a version (``3.12``), an implementation prefix
        (``cpython3.12``), or a
        `version specifier <https://packaging.python.org/en/latest/specifications/version-specifiers/>`_
        (``>=3.10``). When a sequence is given each entry is tried in order.

    :param try_first_with: executables to probe before the normal discovery search. A relative path spec is checked
        first.
    :param cache: interpreter metadata cache; when ``None`` results are not cached.
    :param env: environment mapping for ``PATH`` and uv store lookup; defaults to :data:`os.environ`.
    :param predicate: optional callback applied after an interpreter matches the spec. Return ``True`` to accept the
        interpreter, ``False`` to skip it and continue searching.
    :returns: the first matching interpreter, or ``None`` if no match is found.
    """
    specs = [key] if isinstance(key, str) else key
    for spec_str, preferred_paths in zip(specs, tee(try_first_with or (), len(specs))):
        if result := _find_interpreter(spec_str, preferred_paths, cache, env, predicate):
            return result
    return None


def _find_interpreter(
    key: str,
    try_first_with: Iterable[str],
    cache: PyInfoCache | None = None,
    env: Mapping[str, str] | None = None,
    predicate: Callable[[PythonInfo], bool] | None = None,
) -> PythonInfo | None:
    spec = PythonSpec.from_string_spec(key)
    _LOGGER.info("find interpreter for spec %r", spec)
    proposed_paths: set[tuple[str | None, bool]] = set()
    env = os.environ if env is None else env
    for interpreter, impl_must_match in propose_interpreters(spec, try_first_with, cache, env):
        if interpreter is None:  # pragma: no cover, defensive guard the proposer does not currently trigger
            continue
        proposed_key = interpreter.system_executable, impl_must_match
        if proposed_key in proposed_paths:
            continue
        _LOGGER.info("proposed %s", interpreter)
        if interpreter.satisfies(spec, impl_must_match=impl_must_match) and (
            predicate is None or predicate(interpreter)
        ):
            _LOGGER.debug("accepted %s", interpreter)
            return interpreter
        proposed_paths.add(proposed_key)
    return None


def propose_interpreters(
    spec: PythonSpec,
    try_first_with: Iterable[str],
    cache: PyInfoCache | None = None,
    env: Mapping[str, str] | None = None,
    *,
    all_implementations: bool = False,
) -> Generator[tuple[PythonInfo | None, bool], None, None]:
    # enumeration APIs pass all_implementations to also surface non-CPython binaries on PATH and under UV's install dir
    env = os.environ if env is None else env
    tested_exes: set[str] = set()
    if spec.is_abs and spec.path is not None:
        if exe_raw := _check_exe(spec.path, tested_exes):  # pragma: no branch # first exe always new
            yield PythonInfo.from_exe(exe_raw, cache, env=env), True
        return

    yield from _propose_explicit(spec, try_first_with, cache, env, tested_exes)
    if spec.path is not None and spec.is_abs:  # pragma: no cover # relative spec.path is never abs
        return
    yield from _propose_from_path(spec, cache, env, tested_exes, all_implementations=all_implementations)
    yield from _propose_from_uv(spec, cache, env, all_implementations=all_implementations)


def _check_exe(path: str, tested_exes: set[str]) -> str | None:
    # Resolve *path* to an absolute path and return it if not yet tested, otherwise ``None``.
    try:
        os.lstat(path)
    except OSError:
        return None
    exe_id = fs_path_id(str(Path(path).resolve()))
    if exe_id in tested_exes:
        return None
    tested_exes.add(exe_id)
    # unlike Path.absolute(), abspath collapses "..", which PythonInfo._satisfies_path relies on
    return os.path.abspath(path)


def _propose_explicit(
    spec: PythonSpec,
    try_first_with: Iterable[str],
    cache: PyInfoCache | None,
    env: Mapping[str, str],
    tested_exes: set[str],
) -> Generator[tuple[PythonInfo | None, bool], None, None]:
    # A hint on the same file or base interpreter could otherwise hide the only candidate matching a relative path.
    if spec.path is not None and os.path.dirname(spec.path) and (exe_raw := _check_exe(spec.path, tested_exes)):
        yield PythonInfo.from_exe(exe_raw, cache, env=env), True

    for py_exe in try_first_with:
        if Path(py_exe).exists() and (exe_raw := _check_exe(py_exe, tested_exes)):
            yield PythonInfo.from_exe(exe_raw, cache, env=env), True

    if spec.path is None:
        yield from _propose_current_and_windows(spec, cache, env, tested_exes)


def _propose_current_and_windows(
    spec: PythonSpec,
    cache: PyInfoCache | None,
    env: Mapping[str, str],
    tested_exes: set[str],
) -> Generator[tuple[PythonInfo | None, bool], None, None]:
    current_python = PythonInfo.current_system(cache)
    if _is_new_exe(str(current_python.executable), tested_exes):
        yield current_python, True

    if IS_WIN:  # pragma: win32 cover
        from ._windows import propose_interpreters as win_propose  # ruff:ignore[import-outside-top-level] Windows-only

        for interpreter in win_propose(spec, cache, env):
            if _is_new_exe(str(interpreter.executable), tested_exes):
                yield interpreter, True


def _is_new_exe(exe_raw: str, tested_exes: set[str]) -> bool:
    # Return ``True`` and register *exe_raw* if it hasn't been tested yet.
    exe_id = fs_path_id(exe_raw)
    if exe_id in tested_exes:
        return False
    tested_exes.add(exe_id)
    return True


def _propose_from_path(
    spec: PythonSpec,
    cache: PyInfoCache | None,
    env: Mapping[str, str],
    tested_exes: set[str],
    *,
    all_implementations: bool,
) -> Generator[tuple[PythonInfo | None, bool], None, None]:
    find_candidates = path_exe_finder(spec, all_implementations=all_implementations)
    for pos, path in enumerate(get_paths(env)):
        _LOGGER.debug(LazyPathDump(pos, path, env))
        for exe, impl_must_match in find_candidates(path):
            exe_raw = str(exe)
            if resolved := _resolve_shim(exe_raw, env):
                _LOGGER.debug("resolved shim %s to %s", exe_raw, resolved)
                exe_raw = resolved
            if not _is_new_exe(exe_raw, tested_exes):
                continue
            if (interpreter := PathPythonInfo.from_exe(exe_raw, cache, raise_on_error=False, env=env)) is not None:
                yield interpreter, impl_must_match


def path_exe_finder(
    spec: PythonSpec, *, all_implementations: bool = False
) -> Callable[[Path], Generator[tuple[Path, bool], None, None]]:
    # Given a spec, return a function that can be called on a path to find all matching files in it.
    pat = spec.generate_re(windows=sys.platform == "win32", all_implementations=all_implementations)
    direct = spec.str_spec
    implementation = spec.implementation.lower() if spec.implementation is not None else None
    impl_must_match = implementation in KNOWN_IMPLEMENTATIONS and implementation != "python"
    if sys.platform == "win32" and not direct.lower().endswith(".exe"):  # pragma: win32 cover
        direct = f"{direct}.exe"

    def path_exes(path: Path) -> Generator[tuple[Path, bool], None, None]:
        # an empty spec (enumerating everything) would make the direct path the PATH directory itself
        direct_path = path / direct
        if direct_path.is_file():
            yield direct_path, impl_must_match

        for exe in path.iterdir():
            if (match := pat.fullmatch(exe.name)) and exe.is_file():
                yield exe.absolute(), impl_must_match or match["impl"].lower() == "python"

    return path_exes


def get_paths(env: Mapping[str, str]) -> Generator[Path, None, None]:
    path = env.get("PATH", None)
    if path is None:
        try:
            path = os.confstr("CS_PATH")
        except (AttributeError, ValueError):  # pragma: no cover # Windows only (no confstr)
            path = os.defpath
    if path:
        # Relative entries can execute an interpreter supplied by the working directory.
        for entry in map(Path, filter(None, path.split(os.pathsep))):
            with suppress(OSError):
                if entry.is_absolute() and entry.is_dir() and next(entry.iterdir(), None):
                    yield entry


class LazyPathDump:
    def __init__(self, pos: int, path: Path, env: Mapping[str, str]) -> None:
        self.pos = pos
        self.path = path
        self.env = env

    def __repr__(self) -> str:
        content = f"discover PATH[{self.pos}]={self.path}"
        if self.env.get("_VIRTUALENV_DEBUG"):
            content += " with =>"
            for file_path in self.path.iterdir():
                try:
                    if not self._is_executable(file_path):
                        continue
                except OSError:
                    pass
                content += " "
                content += file_path.name
        return content

    def _is_executable(self, file_path: Path) -> bool:
        if file_path.is_dir():
            return False
        if IS_WIN:  # pragma: win32 cover
            pathext = self.env.get("PATHEXT", ".COM;.EXE;.BAT;.CMD").split(";")
            return any(file_path.name.upper().endswith(ext) for ext in pathext)
        return bool(file_path.stat().st_mode & os.X_OK)


def _resolve_shim(exe_path: str, env: Mapping[str, str]) -> str | None:
    # Resolve a version-manager shim to the actual Python binary.
    version_manager_layouts: list[tuple[str, tuple[str, ...]]] = [
        ("PYENV_ROOT", ("versions",)),
        ("MISE_DATA_DIR", ("installs", "python")),
        ("ASDF_DATA_DIR", ("installs", "python")),
    ]
    for shims_dir_env, versions_path in version_manager_layouts:
        if (root := env.get(shims_dir_env)) and os.path.dirname(exe_path) == os.path.join(root, "shims"):
            return _resolve_shim_to_binary(os.path.basename(exe_path), os.path.join(root, *versions_path), env)
    return None


def _resolve_shim_to_binary(exe_name: str, versions_dir: str, env: Mapping[str, str]) -> str | None:
    for version in _active_versions(env):
        if version in {"", ".", ".."} or basename(version) != version:
            _LOGGER.debug("ignoring invalid version name %r", version)
            continue
        resolved = os.path.join(versions_dir, version, "bin", exe_name)
        if Path(resolved).is_file() and os.access(resolved, os.X_OK):
            return resolved
    return None


def _active_versions(env: Mapping[str, str]) -> Generator[str, None, None]:
    # Yield active Python version strings by reading version-manager configuration.
    if pyenv_version := env.get("PYENV_VERSION"):
        yield from pyenv_version.split(":")
        return
    cwd: str | Path | None
    try:
        cwd = Path.cwd()
    except OSError:  # removed, or on illumos below an unreadable directory; pyenv reads $PWD as well
        cwd = env.get("PWD")
    if cwd and (versions := _read_python_version_file(cwd)):
        yield from versions
        return
    if (pyenv_root := env.get("PYENV_ROOT")) and (
        versions := _read_python_version_file(os.path.join(pyenv_root, "version"), search_parents=False)
    ):
        yield from versions


def _read_python_version_file(start: str | Path, *, search_parents: bool = True) -> list[str] | None:
    # Read a ``.python-version`` file, optionally searching parent directories.
    current = start
    while True:
        # unlike pathlib before 3.14, os.path answers False when a directory on the way can't be searched
        candidate = os.path.join(current, ".python-version") if os.path.isdir(current) else current
        if os.path.isfile(candidate) and (versions := _versions_in_file(candidate)):
            return versions
        if not search_parents:
            return None
        parent = Path(current).parent
        if parent == current:
            return None
        current = parent


def _versions_in_file(path: str | Path) -> list[str]:
    try:
        # pyenv reads raw bytes, so a byte that is not UTF-8 (a Latin-1 comment, say) must not hide the versions
        with Path(path).open(encoding="utf-8", errors="replace") as fh:
            # Version files can sit in shared parent directories; bound the in-process read.
            max_chars = 4096
            content = fh.read(max_chars + 1)
            if len(content) > max_chars:
                _LOGGER.debug("ignored oversized version file %s", path)
                return []
            return [v for line in content.split("\n") if (v := line.strip()) and not v.startswith("#")]
    except OSError:  # skip a file we cannot read, the same as one that names no version
        _LOGGER.debug("failed to read %s", path, exc_info=True)
        return []


class PathPythonInfo(PythonInfo): ...


def _propose_from_uv(
    spec: PythonSpec,
    cache: PyInfoCache | None,
    env: Mapping[str, str],
    *,
    all_implementations: bool,
) -> Generator[tuple[PythonInfo | None, bool], None, None]:
    seen_uv_paths: set[str] = set()
    for root in _uv_python_roots(env):
        for install in _uv_installs(root, spec, all_implementations=all_implementations):
            for exe_path in _uv_executables(install):
                if (resolved := str(exe_path.resolve())) in seen_uv_paths:
                    continue
                seen_uv_paths.add(resolved)
                if interpreter := PathPythonInfo.from_exe(str(exe_path), cache, raise_on_error=False, env=env):
                    yield interpreter, True
                    break  # one install directory holds one interpreter


def _uv_python_roots(env: Mapping[str, str]) -> Generator[Path, None, None]:
    # Yield uv's store roots, legacy first; searching both keeps a stale legacy directory from hiding the live one.
    if install_dir := env.get("UV_PYTHON_INSTALL_DIR"):
        yield Path(install_dir).expanduser()
        return
    for state_dir in _uv_state_dirs(env):
        if state_dir.is_absolute():  # a relative profile path would search the caller's working directory
            yield state_dir / "python"


def _uv_state_dirs(env: Mapping[str, str]) -> Generator[Path, None, None]:
    # Yield uv's legacy state directory then its current one, the order uv prefers them in.
    windows: Final = sys.platform == "win32"
    home: Final = Path(profile) if (profile := env.get("USERPROFILE" if windows else "HOME")) else None
    if windows:
        app_data = Path(roaming) if (roaming := env.get("APPDATA")) else None
        if app_data is None or not app_data.is_absolute():
            app_data = home / "AppData" / "Roaming" if home is not None else None
        if app_data is not None:
            yield app_data / "uv" / "data"
            yield app_data / "uv"
        return
    if sys.platform == "darwin" and home is not None:
        yield home / "Library" / "Application Support" / "uv"
    # uv ignores a relative XDG_DATA_HOME, as the XDG specification requires
    if (xdg_data_home := env.get("XDG_DATA_HOME")) and (xdg := Path(xdg_data_home)).is_absolute():
        yield xdg / "uv"
    elif home is not None:
        yield home / ".local" / "share" / "uv"


def _uv_installs(root: Path, spec: PythonSpec, *, all_implementations: bool) -> list[_UvInstall]:
    try:
        matching = [
            install
            for entry in sorted(root.iterdir())
            if not entry.name.startswith(".")
            and entry.is_dir()
            and _uv_install_matches(install := _parse_uv_install(entry), spec, all_implementations=all_implementations)
        ]
    except OSError:
        return []
    matching.sort(key=_uv_sort_key)  # stable, so equally ranked installs stay in directory name order
    return matching


def _uv_install_matches(install: _UvInstall, spec: PythonSpec, *, all_implementations: bool) -> bool:
    if (key := install.key) is None:
        return True
    if spec.implementation is not None:
        if spec.implementation.lower() != key.implementation:
            return False
    elif not all_implementations and key.implementation != "cpython":
        # uv resolves a bare `3.8` to `cpython-3.8`; on PATH the equivalent probe finds CPython too
        return False
    if spec.free_threaded is not None and spec.free_threaded != key.free_threaded:
        return False
    if spec.debug is not None and spec.debug != key.debug:
        return False
    return _uv_version_matches(key, spec)


def _uv_version_matches(key: _UvKey, spec: PythonSpec) -> bool:
    # GraalPy keys carry the GraalVM version in older uv releases, so only CPython and PyPy state a Python version
    if key.implementation not in {"cpython", "pypy"}:
        return True
    if spec.version_specifier is not None and not all(
        _uv_specifier_matches(key, specifier) for specifier in spec.version_specifier
    ):
        return False
    return all(req is None or our == req for our, req in zip(key.version.release, (spec.major, spec.minor, spec.micro)))


def _uv_specifier_matches(key: _UvKey, specifier: SimpleSpecifier) -> bool:
    if specifier.version is None:
        return False
    # Match at the requested precision, as PythonInfo.satisfies does after probing.
    numeric_version = specifier.version_str
    for prefix in ("rc", "b", "a"):
        if prefix in numeric_version:
            numeric_version = numeric_version.split(prefix)[0]
            break
    precision = numeric_version.count(".") + 1
    release = ".".join(str(part) for part in key.version.release[:precision])
    if key.version.pre_type is not None and (
        precision == 3 or specifier.version.pre_type is not None  # ruff:ignore[magic-value-comparison] full version
    ):
        release = f"{release}{key.version.pre_type}{key.version.pre_num}"
    return specifier.contains(release)


def _parse_uv_install(path: Path) -> _UvInstall:
    implementation, _, remainder = path.name.partition("-")
    version_str, _, variant = remainder.partition("-")[0].partition("+")
    try:
        version = SimpleVersion.from_string(version_str)
    except ValueError:  # not a uv key, but the directory may still hold an interpreter worth probing
        return _UvInstall(path=path, key=None)
    variants = variant.split("+")
    key = _UvKey(
        implementation=implementation.lower(),
        version=version,
        free_threaded="freethreaded" in variants,
        debug="debug" in variants,
    )
    return _UvInstall(path=path, key=key)


@dataclass(**DC_KW)
class _UvInstall:
    path: Path
    key: _UvKey | None


@dataclass(**DC_KW)
class _UvKey:
    # The ``<implementation>-<version>[+<variant>]-<os>-<arch>-<libc>`` name uv gives an install directory.
    implementation: str
    version: SimpleVersion
    free_threaded: bool
    debug: bool


def _uv_sort_key(install: _UvInstall) -> tuple[int, ...]:
    # Rank like uv does: CPython first, newest version first, default build ahead of free-threaded and debug.
    impl_order: Final[tuple[str, ...]] = ("cpython", "pypy", "graalpy", "pyodide")
    if (key := install.key) is None:
        return (len(impl_order) + 1,)
    version = key.version
    return (
        impl_order.index(key.implementation) if key.implementation in impl_order else len(impl_order),
        # uv's minor version links point at a concrete install that moves on upgrade, so report the target instead;
        # spot them by the name they resolve to, as on Windows they are junctions, which is_symlink() does not report
        int(install.path.resolve().name != install.path.name),
        -version.major,
        -version.minor,
        -version.micro,
        -{"a": 0, "b": 1, "rc": 2, None: 3}[version.pre_type],
        -(version.pre_num or 0),
        int(key.free_threaded),
        int(key.debug),
    )


def _uv_executables(install: _UvInstall) -> Generator[Path, None, None]:
    # some distributions unpack into an `install` subdirectory, which uv resolves the same way
    base = nested if (nested := install.path / "install").is_dir() else install.path
    for pattern in (
        "bin/python",
        "python.exe",
        "bin/pypy*",
        "pypy*.exe",
        "bin/graalpy",
        "bin/graalpy.exe",
        "python*t.exe",  # free-threaded Windows builds that ship no python.exe (astral-sh/uv#8298)
    ):
        yield from sorted(base.glob(pattern))


def iter_interpreters(
    key: str | Sequence[str] | None = None,
    try_first_with: Iterable[str] | None = None,
    cache: PyInfoCache | None = None,
    env: Mapping[str, str] | None = None,
    predicate: Callable[[PythonInfo], bool] | None = None,
) -> Iterator[PythonInfo]:
    """
    Yield every interpreter on the system that satisfies *key*.

    Iteration order is discovery order: ``try_first_with`` paths first, then the running interpreter, then ``PATH``
    (left to right), then UV-managed installs. Results are deduplicated by the resolved real path of the underlying
    system interpreter, so symlinked aliases (``/bin`` vs ``/usr/bin``) and venvs that symlink to a base interpreter
    collapse to a single entry. Callers that want a different ordering should sort the result.

    :param key: interpreter specification — same syntax as :func:`get_interpreter`. ``None`` enumerates every Python
        implementation python-discovery knows about (see :data:`KNOWN_IMPLEMENTATIONS`).
    :param try_first_with: executables to probe before the normal discovery search.
    :param cache: interpreter metadata cache; when ``None`` results are not cached. Strongly recommended for
        enumeration, which interrogates every candidate as a subprocess on a cold cache.
    :param env: environment mapping for ``PATH`` and uv store lookup; defaults to :data:`os.environ`.
    :param predicate: optional filter applied after the spec match; return ``True`` to include the interpreter.
    :yields: each matching interpreter, in discovery order.
    """
    if key is None:
        keys: tuple[str | None, ...] = (None,)
    elif isinstance(key, str):
        keys = (key,)
    else:
        keys = tuple(key)
    first_with = tuple(try_first_with or ())
    env_map = os.environ if env is None else env
    seen: set[str] = set()
    for spec_str in keys:
        yield from _iter_for_spec(spec_str, first_with, cache, env_map, predicate, seen)


def _iter_for_spec(  # ruff:ignore[too-many-arguments, too-many-positional-arguments] distinct spec inputs
    spec_str: str | None,
    try_first_with: tuple[str, ...],
    cache: PyInfoCache | None,
    env: Mapping[str, str],
    predicate: Callable[[PythonInfo], bool] | None,
    seen: set[str],
) -> Iterator[PythonInfo]:
    if spec_str is None:
        spec = PythonSpec("", None, None, None, None, None, None)
        wide = True
    else:
        spec = PythonSpec.from_string_spec(spec_str)
        wide = False
    for interpreter, impl_must_match in propose_interpreters(
        spec, try_first_with, cache, env, all_implementations=wide
    ):
        if interpreter is None:
            continue
        if (anchor := interpreter.system_executable or interpreter.executable) is None:
            continue
        if (real_path := os.path.realpath(anchor)) in seen:
            continue
        if not interpreter.satisfies(spec, impl_must_match=impl_must_match):
            continue
        if predicate is not None and not predicate(interpreter):
            continue
        seen.add(real_path)
        yield interpreter


__all__ = [
    "LazyPathDump",
    "get_interpreter",
    "get_paths",
    "iter_interpreters",
    "propose_interpreters",
]
