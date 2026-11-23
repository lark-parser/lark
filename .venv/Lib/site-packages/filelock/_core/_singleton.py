"""Lock instance reuse by path and constructor options."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    assert __spec__ is not None

__lazy_modules__ = [
    "pathlib",
    f"{__spec__.parent}._fork",
    f"{__spec__.parent}._registry",
    f"{__spec__.parent}._shutdown",
]

import os
from abc import ABCMeta
from pathlib import PurePath
from typing import TypeVar, cast

from ._fork import ensure_current_process, fork_transition
from ._registry import canonical, path_key
from ._settings import (
    CONSTRUCTOR_SIGNATURES,
    UNSET_FILE_MODE,
    CloseErrorPolicy,
    ContextErrorPolicy,
    ExtraValue,
    LockInitValue,
    LockOptions,
    check_blocking,
    check_mode,
    override,
    resolve_close_error_policy,
    resolve_context_error_policy,
    resolve_lifetime,
    resolve_on_acquired,
    resolve_poll_interval,
    resolve_preserve_lock_file,
    seconds,
    timeout_behavior,
)
from ._shutdown import resolve_lazy_imports_before_shutdown

if TYPE_CHECKING:
    from collections.abc import Callable
    from threading import RLock
    from weakref import WeakValueDictionary

    from ._lock import BaseFileLock


_T = TypeVar("_T", bound="BaseFileLock")


class FileLockMeta(ABCMeta):
    _instances: WeakValueDictionary[str, BaseFileLock]
    _instances_lock: RLock
    _instances_under_construction: set[str]

    @override
    def __call__(  # ruff:ignore[too-many-arguments]  # forwards the public constructor's documented parameters
        cls: type[_T],
        lock_file: str | os.PathLike[str],
        timeout: float = -1,
        mode: int = UNSET_FILE_MODE,
        thread_local: bool = True,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]  # public positional argument
        *,
        blocking: bool = True,
        is_singleton: bool = False,
        poll_interval: float = 0.05,
        lifetime: float | None = None,
        context_error_policy: ContextErrorPolicy = "chain",
        close_error_policy: CloseErrorPolicy = "default",
        fallback_to_soft: bool = True,
        preserve_lock_file: bool = False,
        on_acquired: Callable[[int], None] | None = None,
        **kwargs: ExtraValue,
    ) -> _T:
        ensure_current_process()
        resolve_lazy_imports_before_shutdown()
        # Validate before __init__: a partial instance can still reach __del__.
        lifetime = resolve_lifetime(lifetime, cls, stacklevel=cls._constructor_lifetime_warning_stacklevel)
        poll_interval = resolve_poll_interval(poll_interval)
        check_blocking(blocking)
        timeout = seconds("timeout", timeout)
        check_mode(mode, cls.__name__)
        options = LockOptions(
            timeout=timeout,
            mode=mode,
            thread_local=thread_local,
            blocking=blocking,
            is_singleton=is_singleton,
            poll_interval=poll_interval,
            lifetime=lifetime,
            context_error_policy=resolve_context_error_policy(context_error_policy),
            close_error_policy=resolve_close_error_policy(close_error_policy),
            fallback_to_soft=fallback_to_soft,
            preserve_lock_file=resolve_preserve_lock_file(
                preserve=preserve_lock_file, supported=cls._preserve_lock_file_supported, cls_name=cls.__name__
            ),
            on_acquired=resolve_on_acquired(on_acquired, supported=cls._on_acquired_supported, cls_name=cls.__name__),
        )
        # A cache hit must reject unknown subclass keywords too.
        with fork_transition():
            signature = CONSTRUCTOR_SIGNATURES.get(cls)
        params = signature.supported(cls.__name__, {**options, **kwargs})
        if is_singleton:
            return FileLockMeta._singleton(cls, lock_file, params, options, kwargs)
        return super().__call__(lock_file, **params)

    def _singleton(
        cls: type[_T],
        lock_file: str | os.PathLike[str],
        params: dict[str, LockInitValue | ExtraValue],
        options: LockOptions,
        extras: dict[str, ExtraValue],
    ) -> _T:
        key = path_key(canonical(lock_file))
        with cls._instances_lock:
            # A chdir or a replaced parent symlink can redirect the cached instance's relative path.
            instance = cls._instances.get(key)
            if instance is None or path_key(canonical(instance._lock_path)) != key:  # ruff:ignore[private-member-access]  # the metaclass owns this instance
                registry = cls._instances_under_construction
                if key in registry:  # pragma: needs fork
                    msg = f"Singleton lock construction is already active for {lock_file!s}"
                    raise RuntimeError(msg)
                pid = os.getpid()
                registry.add(key)
                try:
                    instance = super().__call__(lock_file, **params)
                finally:
                    registry.discard(key)
                if os.getpid() != pid:  # pragma: needs fork
                    msg = "Lock construction cannot continue after fork; construct a new lock in the child"
                    raise RuntimeError(msg)
                cls._instances[key] = instance
                instance._singleton_key = key  # ruff:ignore[private-member-access]  # the finalizer uses this key
                return instance
        _check_cached_options(instance, options, extras)
        if str(PurePath(lock_file)) != str(PurePath(instance.lock_file)):
            instance._singleton_shared = True  # ruff:ignore[private-member-access]  # records aliases of this cached instance
        return cast("_T", instance)


def _check_cached_options(instance: BaseFileLock, options: LockOptions, extras: dict[str, ExtraValue]) -> None:
    mismatches = {
        name: (str(requested), str(existing))
        for name, (requested, existing) in {
            "thread_local": (options["thread_local"], instance.is_thread_local()),
            # Different negative timeouts request the same wait. NaN does not compare equal to itself.
            "timeout": (
                timeout_behavior(options["timeout"], any_negative=True),
                timeout_behavior(instance.timeout, any_negative=True),
            ),
            "mode": (options["mode"], instance._context.mode),  # ruff:ignore[private-member-access]  # compare the stored mode, including its unset sentinel
            "blocking": (options["blocking"], instance.blocking),
            "poll_interval": (options["poll_interval"], instance.poll_interval),
            "lifetime": (options["lifetime"], instance.lifetime),
            "context_error_policy": (options["context_error_policy"], instance.context_error_policy),
            "close_error_policy": (options["close_error_policy"], instance.close_error_policy),
            "fallback_to_soft": (options["fallback_to_soft"], instance.fallback_to_soft),
            "preserve_lock_file": (options["preserve_lock_file"], instance.preserve_lock_file),
        }.items()
        if requested != existing
    }
    mismatches.update(instance._singleton_extra_mismatches(extras))  # ruff:ignore[private-member-access]  # subclass settings participate in singleton identity
    # Equal callables can close over different state.
    hook = options["on_acquired"]
    hook_mismatch = hook is not instance.on_acquired
    if not mismatches and not hook_mismatch:
        return
    msg = "Singleton lock instances cannot be initialized with differing arguments\nNon-matching arguments: "
    for name, (requested, existing) in mismatches.items():
        msg += f"\n\t{name} (existing lock has {existing} but {requested} was passed)"
    if hook_mismatch:
        msg += f"\n\ton_acquired (existing lock has {instance.on_acquired} but {hook} was passed)"
    raise ValueError(msg)


__all__ = [
    "FileLockMeta",
]
