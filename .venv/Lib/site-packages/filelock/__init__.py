"""Cross-platform file locks."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    assert __spec__ is not None

__lazy_modules__ = ["importlib", f"{__spec__.parent}._core"]

import sys
import warnings
from importlib import import_module
from typing import TYPE_CHECKING, Final

# Keeps ``filelock.version`` the string 4.0.12 exposed rather than the submodule.
from filelock.version import version

from ._core import (
    AcquireReturnProxy,
    AcquireWait,
    BaseFileLock,
    CloseErrorPolicy,
    ContextErrorPolicy,
    FileLockContext,
    InFlight,
    LeaseSettingsMismatch,
    LockOptions,
    ReleasePendingError,
    SoftFileLockLifetimeWarning,
    SoftFileLockProtocolError,
    Timeout,
)
from ._native import (
    UnixFileLock,
    WindowsFileLock,
    lock_descriptor,
    unlock_descriptor,
)
from ._native import has_fcntl as unix_has_fcntl

if TYPE_CHECKING:
    from filelock import asyncio
    from filelock.asyncio import (
        AsyncAcquireReturnProxy,
        AsyncSoftFileLease,
        AsyncSoftFileLock,
        AsyncStrictSoftFileLock,
        AsyncUnixFileLock,
        AsyncWindowsFileLock,
        BaseAsyncFileLock,
    )

    from ._soft import (
        AsyncAcquireSoftReadWriteReturnProxy,
        AsyncSoftReadWriteLock,
        CompromiseReason,
        LeaseClaim,
        LeaseCompromise,
        LeaseHeartbeat,
        MarkerSoftFileLock,
        OwnerMode,
        OwnerRecord,
        SoftFileLease,
        SoftFileLock,
        SoftReadWriteLock,
        StrictRelease,
        StrictSoftFileClaim,
        StrictSoftFileClaimState,
        StrictSoftFileLock,
    )
    from ._sqlite import (
        AsyncAcquireReadWriteReturnProxy,
        AsyncReadWriteLock,
        ReadWriteLock,
    )

#: version of the project as a string
__version__: Final[str] = version

#: ``True`` when :func:`fcntl.flock` is available. Off Windows, :data:`FileLock` then resolves to
#: :class:`UnixFileLock`, otherwise to :class:`SoftFileLock`. Always ``False`` on Windows.
#:
#: :meta hide-value:
has_fcntl: Final[bool] = unix_has_fcntl  # simplint: ignore[module-variable-case]  # public API


if sys.platform == "win32":  # pragma: win32 cover
    _FileLock: type[BaseFileLock] = WindowsFileLock
else:  # pragma: win32 no cover # ruff:ignore[collapsible-else-if]  # the else carries the win32 no-cover pragma
    if has_fcntl:
        _FileLock: type[BaseFileLock] = UnixFileLock
    else:
        from ._soft import SoftFileLock

        _FileLock = SoftFileLock
        warnings.warn("only soft file lock is available", stacklevel=2)

if TYPE_CHECKING:
    #: Alias for the lock, which should be used for the current platform.
    FileLock = SoftFileLock
    #: Alias for the async lock, which should be used for the current platform.
    AsyncFileLock = AsyncSoftFileLock
else:
    #: Alias for the lock, which should be used for the current platform.
    FileLock = _FileLock

# Importing asyncio and sqlite3 costs more than the rest of the package, so names that need them load on first access.
_LAZY_ATTRIBUTES: Final[dict[str, str]] = {
    "AsyncAcquireReadWriteReturnProxy": "._sqlite",
    "AsyncAcquireReturnProxy": ".asyncio",
    "AsyncAcquireSoftReadWriteReturnProxy": "._soft",
    "AsyncFileLock": ".asyncio",
    "AsyncReadWriteLock": "._sqlite",
    "AsyncSoftFileLease": ".asyncio",
    "AsyncSoftFileLock": ".asyncio",
    "AsyncSoftReadWriteLock": "._soft",
    "AsyncStrictSoftFileLock": ".asyncio",
    "AsyncUnixFileLock": ".asyncio",
    "AsyncWindowsFileLock": ".asyncio",
    "BaseAsyncFileLock": ".asyncio",
    "CompromiseReason": "._soft",
    "LeaseClaim": "._soft",
    "LeaseCompromise": "._soft",
    "LeaseHeartbeat": "._soft",
    "MarkerSoftFileLock": "._soft",
    "OwnerMode": "._soft",
    "OwnerRecord": "._soft",
    "ReadWriteLock": "._sqlite",
    "SoftFileLease": "._soft",
    "SoftFileLock": "._soft",
    "SoftReadWriteLock": "._soft",
    "StrictRelease": "._soft",
    "StrictSoftFileClaim": "._soft",
    "StrictSoftFileClaimState": "._soft",
    "StrictSoftFileLock": "._soft",
    "asyncio": ".asyncio",
}


def __getattr__(
    name: str,
) -> object:  # simplint: ignore[imprecise-annotation]  # lazy attributes span several types
    if (module_name := _LAZY_ATTRIBUTES.get(name)) is None:
        msg = f"module {__name__!r} has no attribute {name!r}"
        raise AttributeError(msg)
    try:
        module = import_module(module_name, __name__)
        if name == "asyncio":
            value = module
        else:
            value = getattr(module, f"Async{_FileLock.__name__}" if name == "AsyncFileLock" else name)
    except ImportError as error:
        # Only a missing sqlite3 module (the package, CPython's _sqlite3, PyPy's _sqlite3_cffi) leaves the read-write
        # locks None; a frozen application that left out a filelock module gets the error that names it.
        sqlite_missing = (error.name or "").startswith(("sqlite3", "_sqlite3"))
        if module_name != "._sqlite" or not sqlite_missing:
            raise
        value = None  # pragma: lacks sqlite3
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted({*globals(), *_LAZY_ATTRIBUTES})


__all__ = [
    "AcquireReturnProxy",
    "AcquireWait",
    "AsyncAcquireReadWriteReturnProxy",
    "AsyncAcquireReturnProxy",
    "AsyncAcquireSoftReadWriteReturnProxy",
    "AsyncFileLock",
    "AsyncReadWriteLock",
    "AsyncSoftFileLease",
    "AsyncSoftFileLock",
    "AsyncSoftReadWriteLock",
    "AsyncStrictSoftFileLock",
    "AsyncUnixFileLock",
    "AsyncWindowsFileLock",
    "BaseAsyncFileLock",
    "BaseFileLock",
    "CloseErrorPolicy",
    "CompromiseReason",
    "ContextErrorPolicy",
    "FileLock",
    "FileLockContext",
    "InFlight",
    "LeaseClaim",
    "LeaseCompromise",
    "LeaseHeartbeat",
    "LeaseSettingsMismatch",
    "LockOptions",
    "MarkerSoftFileLock",
    "OwnerMode",
    "OwnerRecord",
    "ReadWriteLock",
    "ReleasePendingError",
    "SoftFileLease",
    "SoftFileLock",
    "SoftFileLockLifetimeWarning",
    "SoftFileLockProtocolError",
    "SoftReadWriteLock",
    "StrictRelease",
    "StrictSoftFileClaim",
    "StrictSoftFileClaimState",
    "StrictSoftFileLock",
    "Timeout",
    "UnixFileLock",
    "WindowsFileLock",
    "__version__",
    "asyncio",
    "has_fcntl",
    "lock_descriptor",
    "unlock_descriptor",
]
