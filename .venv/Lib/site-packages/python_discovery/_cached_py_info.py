"""Acquire Python information via subprocess interrogation with multi-level caching."""

from __future__ import annotations

import hashlib
import logging
import os
import pkgutil
import secrets
import sys
import tempfile
from codecs import getincrementaldecoder
from collections import OrderedDict
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from functools import lru_cache
from io import DEFAULT_BUFFER_SIZE, IncrementalNewlineDecoder
from pathlib import Path
from select import select
from shlex import quote

# ruff:ignore[suspicious-subprocess-import] interpreter interrogation
from subprocess import DEVNULL, PIPE, Popen, TimeoutExpired, list2cmdline
from threading import Event, Thread
from time import monotonic
from typing import TYPE_CHECKING, Final, NamedTuple

from ._cache import NoOpCache
from ._py_info import PythonInfo
from ._py_info_collect import MIN_INTERROGATE_VERSION, UNSUPPORTED_EXIT_CODE, UNSUPPORTED_MARKER

if sys.platform == "win32":  # pragma: win32 cover
    from ._windows import stop_query_reader

if TYPE_CHECKING:
    from collections.abc import Generator, Mapping
    from typing import IO, TypedDict

    from ._cache import ContentStore, PyInfoCache

    class CacheEntryMeta(TypedDict):
        # Identity of a cached interrogation result: the queried binary, its arguments and the script.
        st_mtime: float
        path: str
        hash: str | None
        arguments: str | None


_CACHE: Final[OrderedDict[tuple[Path, str | None], PythonInfo | Exception]] = OrderedDict()
_CACHE[Path(sys.executable), None] = PythonInfo()
_LOGGER: Final[logging.Logger] = logging.getLogger(__name__)
_PY_INFO_SCRIPT: Final[Path] = Path(__file__).resolve().parent / "_py_info_collect.py"
# poll(2) limits milliseconds to a signed C int.
_MAX_QUERY_TIMEOUT: Final[float] = (2**31 - 1) / 1000
_MAX_QUERY_OUTPUT: Final[int] = 1 << 20


def from_exe(  # ruff:ignore[too-many-arguments] each argument is a separate probe input
    cls: type[PythonInfo],
    cache: PyInfoCache | None,
    exe: str,
    env: Mapping[str, str] | None = None,
    *,
    raise_on_error: bool = True,
    ignore_cache: bool = False,
    executable_args: str | None = None,
) -> PythonInfo | None:
    env = os.environ if env is None else env
    if cache is None:
        result = _get_from_cache(cls, cache, exe, env, ignore_cache=ignore_cache, executable_args=executable_args)
    else:
        try:
            result = _get_from_cache(cls, cache, exe, env, ignore_cache=ignore_cache, executable_args=executable_args)
        except OSError:
            _LOGGER.debug("failed to use cache for %s", exe, exc_info=True)
            result = _get_from_cache(cls, None, exe, env, ignore_cache=True, executable_args=executable_args)
    if isinstance(result, Exception):
        if raise_on_error:
            raise result
        _LOGGER.info("%s", result)
        result = None
    return result


def _get_from_cache(  # ruff:ignore[too-many-arguments] each argument is a separate probe input
    cls: type[PythonInfo],
    cache: PyInfoCache | None,
    exe: str,
    env: Mapping[str, str],
    *,
    ignore_cache: bool,
    executable_args: str | None,
) -> PythonInfo | Exception:
    key = Path(exe), executable_args
    if not ignore_cache and key in _CACHE:
        result = _CACHE[key]
    else:
        result = _get_via_file_cache(cls, cache, key[0], exe, env, executable_args=executable_args)
        if _cacheable_result(key[0], result):
            _CACHE[key] = result
        else:
            _CACHE.pop(key, None)
    # with launcher arguments the queried binary is not the interpreter, so keep the one the query reported
    if isinstance(result, PythonInfo) and executable_args is None:
        result.executable = exe
    return result


def _get_via_file_cache(  # ruff:ignore[too-many-arguments] each argument is a separate probe input
    cls: type[PythonInfo],
    cache: PyInfoCache | None,
    path: Path,
    exe: str,
    env: Mapping[str, str],
    *,
    executable_args: str | None = None,
) -> PythonInfo | Exception:
    path_text = str(path)
    try:
        path_modified = path.stat().st_mtime
    except OSError:
        path_modified = -1
    try:
        py_info_hash: str | None = _script_hash()
    except OSError:
        py_info_hash = None

    py_info_store = (cache if cache is not None else NoOpCache()).py_info(path)
    entry_meta: CacheEntryMeta = {
        "st_mtime": path_modified,
        "path": path_text,
        "hash": py_info_hash,
        "arguments": executable_args,
    }
    with py_info_store.locked():
        if (cached := _read_cache_entry(cls, py_info_store, entry_meta)) is not None:
            return cached
        failure, py_info = _run_subprocess(cls, exe, env, executable_args)
        if failure is not None and not isinstance(failure, _UnsupportedInterpreterError):
            _LOGGER.debug("first subprocess attempt failed for %s (%s), retrying", exe, failure)
            failure, py_info = _run_subprocess(cls, exe, env, executable_args)
        if isinstance(failure, _UnsupportedInterpreterError):
            _LOGGER.warning("%s", failure)
            if _cacheable_result(path, failure):
                py_info_store.write({**entry_meta, "unsupported": str(failure)})
            return failure
        if failure is not None:
            return failure
        if py_info is None:
            return RuntimeError(f"{exe} failed to produce interpreter info")
        if _cacheable_result(path, py_info):
            py_info_store.write({**entry_meta, "content": py_info.to_dict()})
        return py_info


@lru_cache(maxsize=1)
def _script_hash() -> str:
    return hashlib.sha256(_PY_INFO_SCRIPT.read_bytes()).hexdigest()


def _read_cache_entry(
    cls: type[PythonInfo],
    py_info_store: ContentStore,
    entry_meta: CacheEntryMeta,
) -> PythonInfo | _UnsupportedInterpreterError | None:
    if not py_info_store.exists() or (data := py_info_store.read()) is None:
        return None
    if isinstance(data, dict) and all(data.get(key) == value for key, value in entry_meta.items()):
        if isinstance(unsupported := data.get("unsupported"), str):
            return _UnsupportedInterpreterError(unsupported, entry_meta["path"])
        if isinstance(content := data.get("content"), dict):
            return _load_cached_py_info(cls, py_info_store, content)
    py_info_store.remove()
    return None


def _load_cached_py_info(
    cls: type[PythonInfo],
    py_info_store: ContentStore,
    content: dict,
) -> PythonInfo | None:
    try:
        py_info = cls.from_dict(content.copy())
        stale = (sys_exe := py_info.system_executable) is not None and not Path(sys_exe).is_file()
    except (AttributeError, KeyError, OSError, TypeError, ValueError):
        stale = True
    if stale:
        py_info_store.remove()
        return None
    return py_info


def _run_subprocess(
    cls: type[PythonInfo],
    exe: str,
    env: Mapping[str, str],
    executable_args: str | None = None,
) -> tuple[Exception | None, PythonInfo | None]:
    start_cookie = gen_cookie()
    end_cookie = gen_cookie()
    timeout = _query_timeout(env.get("PY_DISCOVERY_TIMEOUT"))
    with _resolve_py_info_script() as py_info_script:
        cmd: list[str] | str = [exe, str(py_info_script), start_cookie, end_cookie]
        if executable_args is not None:
            # PEP 514 ExecutableArguments is raw command line text, placed before the script per the PEP
            cmd = f"{list2cmdline(cmd[:1])} {executable_args} {list2cmdline(cmd[1:])}"
        env = dict(env)
        env.pop("__PYVENV_LAUNCHER__", None)
        env["PYTHONUTF8"] = "1"
        _LOGGER.debug("get interpreter info via cmd: %s", cmd if isinstance(cmd, str) else LogCmd(cmd))
        try:
            process = Popen(  # ruff:ignore[subprocess-without-shell-equals-true] interrogate discovered interpreter
                cmd,
                universal_newlines=True,
                stdin=DEVNULL,
                stderr=PIPE,
                stdout=PIPE,
                env=env,
                encoding="utf-8",
                errors="backslashreplace",
            )
            out, err, code = _collect_query_output(process, timeout)
        except OSError as os_error:
            out, err, code = "", os_error.strerror, os_error.errno
    if code != 0:
        return _query_failure(exe, out, err, code), None
    out, raw_out, out_starts, out_ends = _extract_between_cookies(out, start_cookie, end_cookie)
    if out_starts < 0 or out_ends < 0:
        _LOGGER.warning("subprocess %s omitted query markers; stdout %d chars", exe, len(raw_out))
        msg = f"{exe} returned output without query markers"
        return RuntimeError(msg), None
    try:
        result = cls.from_json(out)
        if executable_args is None:
            result.executable = exe
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        _LOGGER.warning(
            "subprocess %s returned invalid interpreter information; "
            "raw stdout %d chars, start cookie %s, end cookie %s, "
            "parsed output %d chars: %r",
            exe,
            len(raw_out),
            "found" if out_starts > -1 else "missing",
            "found" if out_ends > -1 else "missing",
            len(out),
            out[:200] if out else "<empty>",
        )
        msg = f"{exe} returned invalid interpreter information (exit code {code}){f', stderr: {err!r}' if err else ''}"
        failure = RuntimeError(msg)
        failure.__cause__ = exc
        return failure, None
    return None, result


def gen_cookie() -> str:
    return secrets.token_hex(_COOKIE_LENGTH // 2)


@lru_cache(maxsize=128)
def _query_timeout(raw: str | None) -> float | None:
    default_query_timeout: float = 15.0
    if raw is None:
        return default_query_timeout
    try:
        timeout = float(raw)
    except ValueError:
        timeout = 0.0
    if timeout > 0:
        return timeout if timeout <= _MAX_QUERY_TIMEOUT else None
    _LOGGER.warning(
        "ignoring PY_DISCOVERY_TIMEOUT=%r, not a positive number of seconds; using %s", raw, default_query_timeout
    )
    return default_query_timeout


@contextmanager
def _resolve_py_info_script() -> Generator[Path]:
    if _PY_INFO_SCRIPT.is_file():
        yield _PY_INFO_SCRIPT
    else:
        data = pkgutil.get_data(__package__ or __name__, _PY_INFO_SCRIPT.name)
        if data is None:
            msg = f"cannot locate {_PY_INFO_SCRIPT.name} for subprocess interrogation"
            raise FileNotFoundError(msg)
        # Python prepends the probe script's directory to sys.path, so keep that directory private.
        with tempfile.TemporaryDirectory() as private_dir:
            script: Final[Path] = Path(private_dir) / _PY_INFO_SCRIPT.name
            script.write_bytes(data)
            yield script


class LogCmd:
    def __init__(self, cmd: list[str], env: Mapping[str, str] | None = None) -> None:
        self.cmd = cmd
        self.env = env

    def __repr__(self) -> str:
        cmd_repr = " ".join(quote(str(c)) for c in self.cmd)
        if self.env is not None:
            cmd_repr = f"{cmd_repr} env of {self.env!r}"
        return cmd_repr


def _collect_query_output(process: Popen[str], timeout: float | None) -> _QueryOutput:
    stdout, stderr = process.stdout, process.stderr
    if stdout is None or stderr is None:
        msg = "query output pipes are required"
        raise ValueError(msg)
    out_chunks: list[str] = []
    err_chunks: list[str] = []
    state = _QueryReadState(process=process, overflow=Event(), stop=Event(), read_errors=[])

    readers = (
        Thread(target=_drain_query_stream, args=(state, stdout, out_chunks), daemon=True),
        Thread(target=_drain_query_stream, args=(state, stderr, err_chunks), daemon=True),
    )
    for reader in readers:
        reader.start()
    if not _query_completed(process, readers, timeout):
        state.stop.set()
        with suppress(OSError):
            process.kill()
        # A descendant may keep the pipes open after the candidate exits.
        process.wait()
        for reader in readers:
            if sys.platform == "win32":  # pragma: win32 cover
                stop_query_reader(reader)
            else:
                reader.join()
        return _QueryOutput("", "timed out", -1)
    if state.read_errors:
        raise state.read_errors[0]
    if state.overflow.is_set():
        return _QueryOutput("", f"produced more than {_MAX_QUERY_OUTPUT} characters of output", -1)
    return _QueryOutput("".join(out_chunks), "".join(err_chunks), process.wait())


@dataclass(frozen=True)
class _QueryReadState:
    process: Popen[str]
    overflow: Event
    stop: Event
    read_errors: list[OSError]


def _drain_query_stream(state: _QueryReadState, stream: IO[str], chunks: list[str]) -> None:
    size = 0
    failed = False
    decoder = IncrementalNewlineDecoder(getincrementaldecoder("utf-8")("backslashreplace"), translate=True)
    with stream:
        while not state.stop.is_set():
            try:
                if sys.platform != "win32" and not select([stream], [], [], 0.05)[0]:  # pragma: win32 cover
                    continue
                data = os.read(stream.fileno(), DEFAULT_BUFFER_SIZE)
            except OSError as error:
                if not state.stop.is_set():  # pragma: win32 cover  # canceled ReadFile raises on Windows
                    state.read_errors.append(error)
                    failed = True
                break
            if chunk := decoder.decode(data, final=not data):
                chunks.append(chunk[: _MAX_QUERY_OUTPUT + 1 - size])
                size += len(chunk)
                if size > _MAX_QUERY_OUTPUT:
                    state.overflow.set()
                    failed = True
                    break
            if not data:
                break
    if failed:
        with suppress(OSError):
            state.process.kill()


def _query_completed(process: Popen[str], readers: tuple[Thread, Thread], timeout: float | None) -> bool:
    deadline = None if timeout is None else monotonic() + timeout
    for reader in readers:
        reader.join(None if deadline is None else max(deadline - monotonic(), 0))
    if any(reader.is_alive() for reader in readers):
        return False
    try:
        process.wait(timeout=None if deadline is None else max(deadline - monotonic(), 0))
    except TimeoutExpired:
        return False
    return True


class _QueryOutput(NamedTuple):
    out: str
    err: str
    code: int


def _query_failure(exe: str, out: str, err: str | None, code: int | None) -> RuntimeError:
    # the gate's exit code and stderr marker must both be present: either alone can collide, an errno of 79 from a
    # failed exec or a shim that echoes the marker phrase, but only the gate produces the combination
    if code == UNSUPPORTED_EXIT_CODE and err is not None and (at := err.find(UNSUPPORTED_MARKER)) != -1:
        details = err[at + len(UNSUPPORTED_MARKER) :].splitlines()
        version = details[0].split() if details else []
        floor = ".".join(str(i) for i in MIN_INTERROGATE_VERSION)
        found = version[0] if version else "unknown"
        msg = f"{exe} is Python {found}, older than the minimum {floor} python-discovery can query"
        return _UnsupportedInterpreterError(msg, details[1].strip() if len(details) > 1 else None)
    msg = f"{exe} with code {code}{f' out: {out!r}' if out else ''}{f' err: {err!r}' if err else ''}"
    return RuntimeError(f"failed to query {msg}")


def _extract_between_cookies(out: str, start_cookie: str, end_cookie: str) -> _CookieSlice:
    # Extract payload between reversed cookie markers, forwarding any surrounding output to stdout.
    raw_out = out
    out_starts = out.find(start_cookie[::-1])
    if out_starts > -1:
        if pre_cookie := out[:out_starts]:
            sys.stdout.write(pre_cookie)
        out = out[out_starts + _COOKIE_LENGTH :]
    out_ends = out.find(end_cookie[::-1])
    if out_ends > -1:
        if post_cookie := out[out_ends + _COOKIE_LENGTH :]:
            sys.stdout.write(post_cookie)
        out = out[:out_ends]
    return _CookieSlice(out, raw_out, out_starts, out_ends)


class _CookieSlice(NamedTuple):
    out: str
    raw_out: str
    out_starts: int
    out_ends: int


class _UnsupportedInterpreterError(RuntimeError):
    # The interpreter is older than the interrogation script supports; retrying cannot help.
    def __init__(self, message: str, executable: str | None = None) -> None:
        super().__init__(message)
        self.executable = executable


def _cacheable_result(path: Path, result: PythonInfo | Exception) -> bool:
    if isinstance(result, PythonInfo):
        executable = result.original_executable
    elif isinstance(result, _UnsupportedInterpreterError):
        executable = result.executable
    else:
        return False
    if executable is None:
        return False
    try:
        return path.samefile(executable)
    except (OSError, TypeError, ValueError):
        return False


_COOKIE_LENGTH: Final[int] = 32


def clear(cache: PyInfoCache) -> None:
    cache.py_info_clear()
    _CACHE.clear()


__all__ = [
    "LogCmd",
    "clear",
    "from_exe",
]
