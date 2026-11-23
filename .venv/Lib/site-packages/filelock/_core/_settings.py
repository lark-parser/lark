"""Lock options, defaults and argument validation."""

from __future__ import annotations

__lazy_modules__ = ["decimal", "inspect", "math", "numbers", "threading", "warnings", "weakref"]

import inspect
import math
import stat
import sys
import time
import warnings
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from numbers import Real
from threading import TIMEOUT_MAX, RLock
from typing import TYPE_CHECKING, Final, Literal, TypedDict, TypeVar, cast
from weakref import WeakKeyDictionary

if TYPE_CHECKING:
    from threading import Lock

    from typing_extensions import override

    from ._lock import BaseFileLock
    from ._state import LockState

elif sys.version_info >= (3, 12):  # pragma: >=3.12 cover
    from typing import override
else:  # pragma: <3.12 cover
    _Method = TypeVar("_Method")

    def override(method: _Method) -> _Method:
        return method


#: Let the filesystem apply umask and inherited ACLs at creation.
UNSET_FILE_MODE: Final[int] = -1

#: How to propagate a context body error together with a release error.
ContextErrorPolicy = Literal["chain", "group"]
#: How to handle a descriptor close error after relinquishing ownership.
CloseErrorPolicy = Literal["default", "raise", "suppress"]
#: Retains the types of additional options forwarded to subclass constructors.
ExtraValue = TypeVar("ExtraValue")
LockInitValue = float | int | bool | str | None | Callable[[int], None]


class LockOptions(TypedDict, total=False):
    """
    Options subclasses can forward to :class:`~filelock.BaseFileLock`.

    :ivar timeout: default wait in seconds. A negative value or infinity waits indefinitely.
    :ivar mode: permissions requested when creating the lock file.
    :ivar thread_local: keep reentrant holds separate for each thread.
    :ivar blocking: wait when another owner holds the lock.
    :ivar is_singleton: reuse one instance per lock class and path.
    :ivar poll_interval: delay between acquisition attempts, in seconds.
    :ivar lifetime: age at which an eligible soft marker can be reclaimed.
    :ivar context_error_policy: how to propagate concurrent body and release errors.
    :ivar close_error_policy: how to handle a descriptor close error.
    :ivar fallback_to_soft: permit a Unix lock to use a soft marker when flock is unavailable.
    :ivar preserve_lock_file: keep the native lock pathname after release.
    :ivar on_acquired: callback receiving the native lock's borrowed descriptor after acquisition.
    """

    timeout: float
    mode: int
    thread_local: bool
    blocking: bool
    is_singleton: bool
    poll_interval: float
    lifetime: float | None
    context_error_policy: ContextErrorPolicy
    close_error_policy: CloseErrorPolicy
    fallback_to_soft: bool
    preserve_lock_file: bool
    on_acquired: Callable[[int], None] | None


@dataclass(frozen=True, slots=True, kw_only=True)
class LockSettings:
    thread_local: bool
    is_singleton: bool
    context_error_policy: ContextErrorPolicy
    close_error_policy: CloseErrorPolicy
    fallback_to_soft: bool
    preserve_lock_file: bool
    on_acquired: Callable[[int], None] | None


def resolve_lifetime(lifetime: float | None, cls: type[LockState], *, stacklevel: int) -> float | None:
    if lifetime is None:
        return None
    # Large integer lifetimes may lose precision when converted to float.
    if isinstance(lifetime, bool) or not isinstance(lifetime, int):
        lifetime = seconds("lifetime", lifetime)
    if lifetime < 0 or (isinstance(lifetime, float) and not math.isfinite(lifetime)):
        msg = f"lifetime must be finite and non-negative, not {lifetime!r}"
        raise ValueError(msg)
    if not cls._lifetime_supported:
        warnings.warn(
            f"lifetime is ignored for {cls.__name__}: {cls._lifetime_unsupported_reason}; "
            f"only SoftFileLock supports lifetime-based expiry",
            stacklevel=stacklevel,
        )
        return None
    if cls._lifetime_replacements is not None:
        strict_lock, lease = cls._lifetime_replacements
        warnings.warn(
            f"{cls.__name__}(lifetime=...) uses age-based expiry and can overlap a live holder; "
            f"use {lease} for expiry or {strict_lock} for fail-closed locking",
            SoftFileLockLifetimeWarning,
            stacklevel=stacklevel,
        )
    return lifetime


def seconds(name: str, value: ExtraValue) -> float:
    # Decimal and Fraction are valid durations. Python also treats bool as a number.
    if isinstance(value, bool) or not isinstance(value, (Real, Decimal)):
        msg = f"{name} must be a number of seconds, not {type(value).__name__}"
        raise TypeError(msg)
    # float() rejects a signaling NaN.
    if isinstance(value, Decimal) and value.is_snan():
        return math.nan
    try:
        seconds: Final[float] = float(value)
    except OverflowError:
        msg = f"{name} is too large to be a number of seconds: {value!r}"
        raise ValueError(msg) from None
    # Preserve negative durations that float() rounds to zero.
    return -math.ulp(0.0) if seconds == 0 and value < 0 else seconds


class SoftFileLockLifetimeWarning(FutureWarning):
    """
    The configured soft-lock lifetime permits overlapping live holders after expiry.

    A :class:`FutureWarning` shows by default wherever the lock is configured; a :class:`DeprecationWarning` shows only
    in ``__main__``.

    """


def resolve_poll_interval(poll_interval: float) -> float:
    if (poll_interval := seconds("poll_interval", poll_interval)) < 0 or not math.isfinite(poll_interval):
        msg = f"poll_interval must be finite and non-negative, not {poll_interval!r}"
        raise ValueError(msg)
    check_timeout_max("poll_interval", poll_interval)
    return poll_interval


def check_timeout_max(name: str, value: float) -> None:
    # Lock.acquire, Event.wait and time.sleep raise OverflowError past this bound, which is only ~49.7 days on Windows.
    if value > TIMEOUT_MAX:
        msg = f"{name} must not exceed threading.TIMEOUT_MAX ({TIMEOUT_MAX}), got {value!r}"
        raise ValueError(msg)


def check_mode(mode: int, cls_name: str) -> None:
    if mode == UNSET_FILE_MODE:
        return
    if isinstance(mode, bool) or not isinstance(mode, int):
        msg = f"mode must be an int, not {type(mode).__name__}"
        raise TypeError(msg)
    if not 0 <= mode <= (stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO):
        msg = f"mode={mode:#o} must be within 0o000-0o777 for {cls_name}"
        raise ValueError(msg)
    # Reopening a marker requires both permissions.
    if ~mode & (stat.S_IRUSR | stat.S_IWUSR):
        msg = f"mode={mode:#o} must grant the owner read and write for {cls_name}"
        raise ValueError(msg)


def resolve_context_error_policy(policy: str) -> ContextErrorPolicy:
    if policy not in frozenset({"chain", "group"}):
        msg = f"context_error_policy must be 'chain' or 'group', got {policy!r}"
        raise ValueError(msg)
    return cast("ContextErrorPolicy", policy)


def resolve_close_error_policy(policy: str) -> CloseErrorPolicy:
    if policy not in frozenset({"default", "raise", "suppress"}):
        msg = f"close_error_policy must be 'default', 'raise', or 'suppress', got {policy!r}"
        raise ValueError(msg)
    return cast("CloseErrorPolicy", policy)


def resolve_preserve_lock_file(*, preserve: bool, supported: bool, cls_name: str) -> bool:
    # Existence locks release by unlinking their marker.
    if preserve and not supported:
        msg = f"preserve_lock_file=True is not supported by {cls_name}: unlinking its marker is how it releases"
        raise ValueError(msg)
    return preserve


def resolve_on_acquired(
    on_acquired: Callable[[int], None] | None, *, supported: bool, cls_name: str
) -> Callable[[int], None] | None:
    if on_acquired is None:
        return None
    # Writing to a soft marker would overwrite its ownership record.
    if not supported:
        msg = f"on_acquired is not supported by {cls_name}: only native locks expose the lock descriptor"
        raise ValueError(msg)
    return on_acquired


def timeout_behavior(timeout: float, *, any_negative: bool) -> float | str:
    if math.isnan(timeout):
        return "nan"
    return -1.0 if timeout == math.inf or (any_negative and timeout < 0) else timeout


def resolve_read_write_timeout(timeout: float, *, blocking: bool) -> float:
    # SQLite gives a zero timeout different semantics from the lock API.
    check_blocking(blocking)
    if (timeout := resolve_timeout(timeout, blocking=blocking)) < 0 and timeout != -1 and blocking:
        msg = f"timeout must be a non-negative number or -1, not {timeout!r}"
        raise ValueError(msg)
    return timeout


def check_blocking(blocking: bool) -> None:  # ruff:ignore[boolean-type-hint-positional-argument]  # validates the option's own value
    if not isinstance(blocking, bool):
        msg = f"blocking must be a bool, not {type(blocking).__name__}"
        raise TypeError(msg)


def resolve_timeout(timeout: float, *, blocking: bool) -> float:
    if math.isnan(timeout := seconds("timeout", timeout)) and blocking:
        msg = "timeout must be a number of seconds, not nan"
        raise ValueError(msg)
    # Deadlock detection recognizes a negative timeout as unlimited.
    return -1 if timeout == math.inf else timeout


def acquire_thread_lock(
    lock: Lock, *, blocking: bool, timeout: float, poll_interval: float, cancel_check: Callable[[], bool] | None
) -> bool:
    if not blocking:
        return lock.acquire(blocking=False)
    if cancel_check is None:
        # Lock.acquire raises OverflowError past TIMEOUT_MAX, which is 49.7 days on Windows.
        return lock.acquire() if timeout == -1 else lock.acquire(timeout=min(timeout, TIMEOUT_MAX))
    deadline = None if timeout == -1 else time.perf_counter() + timeout
    while not lock.acquire(
        timeout=poll_interval if deadline is None else min(poll_interval, max(deadline - time.perf_counter(), 0))
    ):
        if cancel_check() or (deadline is not None and time.perf_counter() >= deadline):
            return False
    return True


class _ConstructorSignature:
    def __init__(self, cls: type[BaseFileLock]) -> None:
        parameters = inspect.signature(cls.__init__).parameters.values()
        self._accepted = frozenset(
            parameter.name
            for parameter in parameters
            if parameter.kind in {inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY}
        )
        self._accepts_kwargs = any(parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters)
        self._defaults = {
            name: parameter.default
            for name, parameter in inspect.signature(type(cls).__call__).parameters.items()
            if parameter.default is not inspect.Parameter.empty
        }

    def supported(
        self, cls_name: str, params: dict[str, LockInitValue | ExtraValue]
    ) -> dict[str, LockInitValue | ExtraValue]:
        if self._accepts_kwargs:
            return params
        if unsupported := sorted(
            name
            for name, value in params.items()
            if name not in self._accepted and (name not in self._defaults or value != self._defaults[name])
        ):
            msg = f"{cls_name} does not support non-default lock options: {', '.join(unsupported)}"
            raise TypeError(msg)
        # Some subclasses narrow __init__. Omit inherited defaults they cannot accept.
        return {name: value for name, value in params.items() if name in self._accepted}


class _ConstructorSignatures:
    def __init__(self) -> None:
        self._lock = RLock()
        # A strong cache would keep dynamically created subclasses alive.
        self._models: WeakKeyDictionary[type[BaseFileLock], _ConstructorSignature] = WeakKeyDictionary()

    def get(self, cls: type[BaseFileLock]) -> _ConstructorSignature:
        with self._lock:
            if (model := self._models.get(cls)) is None:
                self._models[cls] = model = _ConstructorSignature(cls)
            return model

    def clear(self) -> None:
        # A vanished parent thread may still own the inherited lock.
        self._lock = RLock()
        self._models.clear()


CONSTRUCTOR_SIGNATURES: Final[_ConstructorSignatures] = _ConstructorSignatures()


__all__ = [
    "CONSTRUCTOR_SIGNATURES",
    "UNSET_FILE_MODE",
    "CloseErrorPolicy",
    "ContextErrorPolicy",
    "ExtraValue",
    "LockInitValue",
    "LockOptions",
    "LockSettings",
    "SoftFileLockLifetimeWarning",
    "acquire_thread_lock",
    "check_blocking",
    "check_mode",
    "check_timeout_max",
    "override",
    "resolve_close_error_policy",
    "resolve_context_error_policy",
    "resolve_lifetime",
    "resolve_on_acquired",
    "resolve_poll_interval",
    "resolve_preserve_lock_file",
    "resolve_read_write_timeout",
    "resolve_timeout",
    "seconds",
    "timeout_behavior",
]
