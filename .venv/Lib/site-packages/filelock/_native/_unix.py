"""Unix file locking with flock and an optional soft-lock fallback."""

from __future__ import annotations

__lazy_modules__ = ["filelock._filesystem", "pathlib", "secrets", "warnings"]

import os
import secrets
import stat
import sys
import warnings
from contextlib import contextmanager, suppress
from errno import EACCES, EAGAIN, ENOSYS, EWOULDBLOCK
from pathlib import Path
from typing import TYPE_CHECKING, Final, cast

from filelock._core import BaseFileLock, canonical, override, resolve_lifetime
from filelock._filesystem import (
    break_marker_path,
    exchange_back,
    exchange_names,
    exchange_supported,
    foreign_owner,
    open_into,
    write_break_marker,
)

if TYPE_CHECKING:
    from collections.abc import Generator

    from filelock._soft import SoftFileLock


#: FileLock uses the soft backend when flock is unavailable.
has_fcntl = False
if sys.platform == "win32":  # pragma: win32 cover

    class UnixFileLock(BaseFileLock):
        """Native Unix lock; acquisition requires :func:`fcntl.flock`."""

        @override
        def _acquire(self) -> None:
            raise NotImplementedError

        @override
        def _release(self) -> None:
            raise NotImplementedError

else:  # pragma: win32 no cover
    try:
        import fcntl

        _ = (fcntl.flock, fcntl.LOCK_EX, fcntl.LOCK_NB, fcntl.LOCK_UN)
    except (ImportError, AttributeError):
        _FCNTL_UNAVAILABLE: Final[str] = "fcntl is unavailable"

        def lock_fd_nonblocking(_fd: int) -> bool:
            raise OSError(ENOSYS, _FCNTL_UNAVAILABLE)

        def unlock_fd(_fd: int) -> None:
            raise OSError(ENOSYS, _FCNTL_UNAVAILABLE)

    else:
        #: All four flock operations are available.
        has_fcntl = True
        # Some filesystems report EACCES for contention.
        _CONTENTION_ERRNOS: Final[frozenset[int]] = frozenset({EACCES, EAGAIN, EWOULDBLOCK})

        def lock_fd_nonblocking(fd: int) -> bool:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exception:
                if exception.errno in _CONTENTION_ERRNOS:
                    return False
                raise
            return True

        def unlock_fd(fd: int) -> None:
            fcntl.flock(fd, fcntl.LOCK_UN)

    def _flock_is_missing(fd: int) -> bool:
        try:
            lock_fd_nonblocking(fd)
        except OSError as exception:
            if exception.errno is None:
                raise
            return exception.errno == ENOSYS
        return False  # a flock the probe won is released when the caller closes fd

    class UnixFileLock(BaseFileLock):
        """Lock with :func:`fcntl.flock`. The file stays in place on release so waiters share the same inode."""

        @BaseFileLock.lifetime.setter
        @override
        def lifetime(self, value: float | None) -> None:
            if self._soft_fallback_for_path():
                from filelock._soft import SoftFileLock  # ruff:ignore[import-outside-top-level]  # fallback

                backend = SoftFileLock
            else:
                backend = type(self)
            self._context.lifetime = resolve_lifetime(value, backend, stacklevel=3)

        def _soft_fallback_for_path(self) -> bool:
            if self._context.claim_root is not None:
                return self._context.soft_fallback
            return canonical(self.lock_file) in self._flockless_roots

        @property
        def pid(self) -> int | None:
            """Read the holder's PID from the soft fallback marker."""
            with self._soft_marker() as soft:
                return soft.pid

        @contextmanager
        def _soft_marker(self) -> Generator[SoftFileLock]:
            if not self._soft_fallback_for_path():
                msg = "marker access requires a soft fallback on the current lock path"
                raise AttributeError(msg)
            with self._soft_lock() as soft:
                yield soft

        @contextmanager
        def _soft_lock(self) -> Generator[SoftFileLock]:
            from filelock._soft import SoftFileLock  # ruff:ignore[import-outside-top-level]  # fallback

            soft = object.__new__(SoftFileLock)
            soft.__dict__ = self.__dict__
            try:
                yield soft
            finally:
                # Its finalizer must not release the real lock's hold.
                soft.__dict__ = {}

        @property
        def is_lock_held_by_us(self) -> bool:
            """Whether the soft fallback marker identifies this process."""
            with self._soft_marker() as soft:
                return soft.is_lock_held_by_us

        @override
        def _pin_lock_path(self, canonical: str) -> None:
            super()._pin_lock_path(canonical)
            self._context.soft_fallback = canonical in self._flockless_roots

        @override
        def _acquire(self) -> None:
            if self._context.soft_fallback or self._acquire_native():
                with self._soft_lock() as soft:
                    soft._acquire()  # ruff:ignore[private-member-access]  # shares the real lock's state

        def _acquire_native(self) -> bool:
            created: list[int] = []
            existing: list[int] = []
            try:
                fd = self._open_lock_file(created, existing)
                return fd is not None and self._needs_soft_acquire(fd, created)
            except BaseException:
                if created and not self.is_locked:
                    self._discard_interrupted_open(created[0])
                raise
            finally:
                if (opened := created or existing) and self._context.lock_file_fd != opened[0]:
                    try:
                        if self._context.pending_lock_file_fd == opened[0]:
                            self._mark_descriptor_released()
                    finally:
                        os.close(opened[0])

        def _open_lock_file(self, created: list[int], existing: list[int]) -> int | None:
            # Only a newly created inode may become the fallback marker. O_NONBLOCK preserves the caller's deadline
            # on a leased file, and existing contents belong to the holder.
            open_flags = os.O_RDWR | os.O_NONBLOCK
            if (o_nofollow := getattr(os, "O_NOFOLLOW", None)) is not None:
                open_flags |= o_nofollow
            open_mode = self._open_mode()
            if open_mode & (stat.S_IWGRP | stat.S_IWOTH) and self._allows_soft_fallback():
                if os.path.lexists(self._lock_path):
                    return self._open_existing_lock_file(existing, open_flags, open_mode)
                open_mode = self._probed_create_mode(open_mode)
            try:
                return open_into(created, self._lock_path, open_flags | os.O_CREAT | os.O_EXCL, open_mode)
            except OSError as exception:
                if created:
                    raise
                if isinstance(exception, FileNotFoundError):
                    if (
                        self._lock_path
                        and not self._lock_path.endswith(os.sep)
                        and Path(self._lock_path).parent.exists()
                    ):
                        return None
                    raise
                if not isinstance(exception, FileExistsError) and not (
                    isinstance(exception, PermissionError) and Path(self._lock_path).exists()
                ):
                    raise
            return self._open_existing_lock_file(existing, open_flags, open_mode)

        def _allows_soft_fallback(self) -> bool:
            return (
                self._settings.fallback_to_soft
                and not self._settings.preserve_lock_file
                and self._settings.on_acquired is None
            )

        def _open_existing_lock_file(self, existing: list[int], open_flags: int, open_mode: int) -> int | None:
            try:
                return open_into(existing, self._lock_path, open_flags, open_mode)
            except (FileNotFoundError, BlockingIOError, PermissionError) as exception:
                if existing:
                    raise
                if not isinstance(exception, PermissionError):
                    return None  # removed or leased since the create attempt
                # A peer's soft marker only needs read access. A native lock still needs write access.
                try:
                    fd = open_into(existing, self._lock_path, open_flags & ~os.O_RDWR | os.O_RDONLY, open_mode)
                except (FileNotFoundError, BlockingIOError):
                    if existing:
                        raise
                    return None
                if _flock_is_missing(fd):
                    return fd
                raise

        def _probed_create_mode(self, open_mode: int) -> int:
            # A later chmod cannot revoke a descriptor opened before flock reports ENOSYS.
            missing = self._directory_lacks_flock()
            if missing is not False:
                open_mode &= ~(stat.S_IWGRP | stat.S_IWOTH)
            if missing:
                self._fallback_to_soft_lock()
            return open_mode

        def _directory_lacks_flock(self) -> bool | None:
            opened: list[int] = []
            probes: dict[int, list[int]] = self.__dict__.setdefault("_flock_probes", {})
            try:
                probes[id(opened)] = opened
                return self._probe_directory(opened)
            finally:
                try:
                    self._close_probe(opened)
                finally:
                    # An interruption on entry to close leaves the descriptor in its slot.
                    if opened:
                        self._close_probe(opened)
                    probes.pop(id(opened), None)

        def _probe_directory(self, opened: list[int]) -> bool | None:
            directory = Path(self._lock_path).parent
            if anonymous := getattr(os, "O_TMPFILE", 0):  # pragma: linux cover
                fd = self._open_probe(opened, str(directory), anonymous | os.O_RDWR | os.O_EXCL)
                if fd is not None:
                    return _flock_is_missing(fd)
            name = directory / f".filelock-probe-{secrets.token_hex(16)}"
            try:
                fd = self._open_probe(opened, str(name), os.O_RDWR | os.O_CREAT | os.O_EXCL)
                self._unlink_probe(name, opened)
            except BaseException:
                self._unlink_probe(name, opened)
                raise
            return None if fd is None else _flock_is_missing(fd)

        @staticmethod
        def _open_probe(opened: list[int], path: str, flags: int) -> int | None:
            try:
                return open_into(opened, path, flags, 0o600)
            except OSError as exception:
                if opened or exception.errno is None:
                    raise
                return None

        @staticmethod
        def _unlink_probe(name: Path, opened: list[int]) -> None:
            if opened:
                with suppress(FileNotFoundError):
                    if os.path.samestat(name.lstat(), os.fstat(opened[0])):
                        name.unlink()

        @staticmethod
        def _close_probe(opened: list[int]) -> None:
            if opened:
                # Child reset and normal cleanup may both run. Retire and close once in a chain of C calls.
                list(map(os.close, map(opened.pop, (0,))))

        def _fallback_to_soft_lock(self) -> None:
            with self._transition_lock:
                if self._lock_path not in self._flockless_roots:
                    warnings.warn("flock not supported on this filesystem, falling back to SoftFileLock", stacklevel=2)
                    self._flockless_roots |= {self._lock_path}
            self._context.soft_fallback = True

        def _needs_soft_acquire(self, fd: int, created: list[int]) -> bool:
            self._mark_descriptor_pending(fd)
            if not self._context.soft_fallback:
                try:
                    locked = lock_fd_nonblocking(fd)
                except OSError as exception:
                    if exception.errno != ENOSYS or not self._allows_soft_fallback():
                        raise
                    self._fallback_to_soft_lock()
                else:
                    if created:
                        self._apply_explicit_mode(fd)
                    if locked:
                        self._finalize_locked_fd(fd)
                    return False
            if created:
                self._adopt_created_file(fd, created)
            return not self.is_locked

        def _apply_explicit_mode(self, fd: int) -> None:
            if self.has_explicit_mode:
                with suppress(PermissionError):
                    os.fchmod(fd, self._context.mode)

        def _finalize_locked_fd(self, fd: int) -> None:
            # A peer may have unlinked this inode before flock succeeded.
            if (stat_result := os.fstat(fd)).st_nlink == 0:
                return
            parent = Path(self._lock_path).parent.stat()
            # A callback can overwrite another file through a hard link planted in a shared directory.
            if (
                stat_result.st_nlink > 1
                and self._settings.on_acquired is not None
                and (parent.st_uid not in {os.geteuid(), 0} or parent.st_mode & (stat.S_IWGRP | stat.S_IWOTH))
            ):
                reason = "lock file has another hard link where other accounts can write; on_acquired cannot take it"
                raise PermissionError(EACCES, reason, self._lock_path)
            # Another owner in a sticky directory can replace this inode during the hold.
            if (owner := foreign_owner(stat_result, parent, fd=fd)) is not None:  # pragma: needs foreign-sticky-tmp
                reason = f"lock file belongs to uid {owner}, not to this process's account or the directory's owner"
                raise PermissionError(EACCES, reason, self._lock_path)
            self._mark_descriptor_owned(fd, (stat_result.st_dev, stat_result.st_ino))

        def _adopt_created_file(self, fd: int, created: list[int]) -> None:
            marker = os.fstat(fd)
            with self._soft_lock() as soft, suppress(FileNotFoundError):
                if not os.path.samestat(os.lstat(self._lock_path), marker):
                    return
                if marker.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
                    # chmod cannot revoke write access through an already-open descriptor.
                    if exchange_supported():
                        self._exchange_created_file(soft, marker, created)
                    if not self.is_locked and os.path.samestat(os.lstat(self._lock_path), marker):
                        raise PermissionError(EACCES, "soft fallback needs a private marker", self._lock_path)
                    return
                soft._apply_explicit_mode(fd)  # ruff:ignore[private-member-access]  # same lock state
                soft._write_lock_info(fd)  # ruff:ignore[private-member-access]  # same lock state
                if os.path.samestat(os.lstat(self._lock_path), marker):
                    self._mark_descriptor_owned(fd, (marker.st_dev, marker.st_ino))

        def _exchange_created_file(self, soft: SoftFileLock, marker: os.stat_result, created: list[int]) -> None:
            try:
                soft._take_over_by_exchange(marker, None)  # ruff:ignore[private-member-access]  # same lock state
            finally:
                if self.is_locked:
                    self._close_probe(created)

        def _discard_interrupted_open(self, fd: int) -> None:
            if not self._allows_soft_fallback() or not (self._context.soft_fallback or _flock_is_missing(fd)):
                return
            if exchange_supported():
                with suppress(OSError):
                    self._replace_unfinished_marker(fd)

        def _replace_unfinished_marker(self, fd: int) -> None:
            marker = os.fstat(fd)
            if not os.path.samestat(os.lstat(self._lock_path), marker):
                return
            aside = break_marker_path(self._lock_path, os.getpid())
            opened: list[int] = []
            try:
                pin = open_into(opened, aside, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                write_break_marker(pin)
                exchange_names(aside, self._lock_path)
            finally:
                for pin in opened:
                    try:
                        if os.path.samestat(os.lstat(aside), marker):
                            Path(aside).unlink()
                        else:
                            exchange_back(self._lock_path, aside, pin)
                    finally:
                        os.close(pin)

        @override
        def _reset_after_fork_in_child(self) -> None:  # pragma: forked child
            for opened in self.__dict__.pop("_flock_probes", {}).values():
                with suppress(OSError):
                    self._close_probe(opened)
            super()._reset_after_fork_in_child()

        @override
        def _unprobeable_holder(self) -> str | None:
            if not self._context.soft_fallback:
                return None
            with self._soft_lock() as soft:
                return soft._unprobeable_holder()  # ruff:ignore[private-member-access]  # reads the soft marker

        @override
        def _try_break_expired_lock(self) -> None:
            if self._context.soft_fallback:
                with self._soft_lock() as soft:
                    soft._try_break_expired_lock()  # ruff:ignore[private-member-access]  # expires the soft marker

        def break_lock(self) -> None:
            """
            Remove this lock's soft marker on its resolved path.

            :raises RuntimeError: if the current path has not entered a soft fallback

            """
            if not self._soft_fallback_for_path():
                msg = "break_lock requires a soft fallback on the current lock path"
                raise RuntimeError(msg)
            with self._soft_lock() as soft:
                soft.break_lock()

        @override
        def _release(self) -> None:
            if self._context.soft_fallback:
                with self._soft_lock() as soft:
                    soft._release()  # ruff:ignore[private-member-access]  # releases the soft marker
                return
            fd = cast("int", self._context.lock_file_fd)
            # A signal can raise after the kernel unlocked but before Python recorded it.
            self._context.unlock_uncertain = True
            unlock_fd(fd)
            self._mark_descriptor_released()
            self._close_released_fd(fd, default_suppresses=True)


if sys.platform == "win32":  # pragma: win32 cover
    __all__ = ["UnixFileLock", "has_fcntl"]
else:  # pragma: win32 no cover
    __all__ = ["UnixFileLock", "has_fcntl", "lock_fd_nonblocking", "unlock_fd"]
