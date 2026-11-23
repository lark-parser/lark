"""Shared lifecycle, options and errors for the locking backends."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    assert __spec__ is not None

__lazy_modules__ = [
    f"{__spec__.parent}._acquire",
    f"{__spec__.parent}._errors",
    f"{__spec__.parent}._fork",
    f"{__spec__.parent}._lock",
    f"{__spec__.parent}._registry",
    f"{__spec__.parent}._settings",
    f"{__spec__.parent}._shutdown",
    f"{__spec__.parent}._singleton",
    f"{__spec__.parent}._state",
]

from ._acquire import AcquireReturnProxy, ReadWriteBackend
from ._errors import (
    LeaseSettingsMismatch,
    ReleasePendingError,
    SoftFileLockProtocolError,
    Timeout,
    append_exception_context,
    grouped_errors,
    is_system_call_failure,
    raise_body_and_release,
    raise_chained_errors,
    raise_cleanup_errors,
    raise_grouped_errors,
)
from ._fork import (
    ForkClassResettable,
    ForkDescriptorOwner,
    ForkResettable,
    ensure_current_process,
    fork_transition,
    register_fork_class,
    register_fork_object,
    register_owned_descriptor,
    unregister_owned_descriptor,
)
from ._lock import BaseFileLock
from ._registry import canonical, path_key
from ._settings import (
    UNSET_FILE_MODE,
    CloseErrorPolicy,
    ContextErrorPolicy,
    ExtraValue,
    LockOptions,
    LockSettings,
    SoftFileLockLifetimeWarning,
    acquire_thread_lock,
    check_blocking,
    check_timeout_max,
    override,
    resolve_lifetime,
    resolve_poll_interval,
    resolve_read_write_timeout,
    resolve_timeout,
    seconds,
    timeout_behavior,
)
from ._shutdown import interpreter_exiting, resolve_lazy_imports_before_shutdown
from ._singleton import FileLockMeta
from ._state import AcquireWait, FileLockContext, InFlight, ThreadLocalFileContext, delegate_to_current, on_this_stack

__all__ = [
    "UNSET_FILE_MODE",
    "AcquireReturnProxy",
    "AcquireWait",
    "BaseFileLock",
    "CloseErrorPolicy",
    "ContextErrorPolicy",
    "ExtraValue",
    "FileLockContext",
    "FileLockMeta",
    "ForkClassResettable",
    "ForkDescriptorOwner",
    "ForkResettable",
    "InFlight",
    "LeaseSettingsMismatch",
    "LockOptions",
    "LockSettings",
    "ReadWriteBackend",
    "ReleasePendingError",
    "SoftFileLockLifetimeWarning",
    "SoftFileLockProtocolError",
    "ThreadLocalFileContext",
    "Timeout",
    "acquire_thread_lock",
    "append_exception_context",
    "canonical",
    "check_blocking",
    "check_timeout_max",
    "delegate_to_current",
    "ensure_current_process",
    "fork_transition",
    "grouped_errors",
    "interpreter_exiting",
    "is_system_call_failure",
    "on_this_stack",
    "override",
    "path_key",
    "raise_body_and_release",
    "raise_chained_errors",
    "raise_cleanup_errors",
    "raise_grouped_errors",
    "register_fork_class",
    "register_fork_object",
    "register_owned_descriptor",
    "resolve_lazy_imports_before_shutdown",
    "resolve_lifetime",
    "resolve_poll_interval",
    "resolve_read_write_timeout",
    "resolve_timeout",
    "seconds",
    "timeout_behavior",
    "unregister_owned_descriptor",
]
