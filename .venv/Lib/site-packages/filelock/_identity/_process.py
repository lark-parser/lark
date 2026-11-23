"""Process identity and liveness checks for recorded lock owners."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    assert __spec__ is not None

__lazy_modules__ = ["pathlib", f"{__spec__.parent}._host"]

import os
import sys
from errno import EPERM, ESRCH
from pathlib import Path
from typing import Final

from ._host import NAMESPACE_MARK, host_name


def owner_is_stale(pid: int, hostname: str, start_token: int | None) -> bool:
    # A foreign hostname or unreadable start token cannot establish that a live PID was recycled.
    if hostname != host_name():
        return False
    if process_alive(pid) and (
        start_token is None or (current := process_start_token(pid)) is None or _same_start(current, start_token)
    ):
        return False
    # Only a bare hostname can be an older release's, written from a container that shares this host's name.
    return NAMESPACE_MARK in hostname or not _owner_runs_elsewhere(pid, start_token)


def _same_start(current: int, recorded: int) -> bool:
    # A hidden boot ID leaves only the low 64 bits (start time) comparable.
    return current == recorded or (0 in {current >> 64, recorded >> 64} and current % 2**64 == recorded % 2**64)


def owner_is_current_process(pid: int, hostname: str, start_token: int | None) -> bool:
    if pid != os.getpid() or hostname != host_name():
        return False
    return start_token is None or start_token == process_start_token(pid)


if sys.platform == "win32":  # pragma: win32 cover
    import ctypes
    from ctypes import wintypes

    _KERNEL32: Final[ctypes.WinDLL] = ctypes.WinDLL("kernel32", use_last_error=True)
    _KERNEL32.CloseHandle.argtypes = [wintypes.HANDLE]
    _KERNEL32.CloseHandle.restype = wintypes.BOOL
    _KERNEL32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _KERNEL32.OpenProcess.restype = wintypes.HANDLE
    _KERNEL32.GetProcessTimes.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
    ]
    _KERNEL32.GetProcessTimes.restype = wintypes.BOOL
    _KERNEL32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    _KERNEL32.WaitForSingleObject.restype = wintypes.DWORD

    _WIN_SYNCHRONIZE: Final[int] = 0x100000
    _WIN_PROCESS_QUERY_LIMITED_INFORMATION: Final[int] = 0x1000
    _WIN_ERROR_INVALID_PARAMETER: Final[int] = 87
    _WIN_INHERIT_HANDLE: Final[bool] = False
    _WIN_WAIT_OBJECT_0: Final[int] = 0

    def process_alive(pid: int) -> bool:
        if handle := _KERNEL32.OpenProcess(_WIN_SYNCHRONIZE, _WIN_INHERIT_HANDLE, pid):
            try:
                # Any open handle keeps an exited process openable, but its process object is signaled once it exits.
                return _KERNEL32.WaitForSingleObject(handle, 0) != _WIN_WAIT_OBJECT_0
            finally:
                _KERNEL32.CloseHandle(handle)
        return ctypes.get_last_error() != _WIN_ERROR_INVALID_PARAMETER

    def process_start_token(pid: int) -> int | None:
        handle = _KERNEL32.OpenProcess(_WIN_PROCESS_QUERY_LIMITED_INFORMATION, _WIN_INHERIT_HANDLE, pid)
        if not handle:
            return None
        creation, exit_time, kernel_time, user_time = (wintypes.FILETIME() for _ in range(4))
        try:
            if not _KERNEL32.GetProcessTimes(
                handle,
                ctypes.byref(creation),
                ctypes.byref(exit_time),
                ctypes.byref(kernel_time),
                ctypes.byref(user_time),
            ):
                return None  # pragma: no cover  # win32 GetProcessTimes failure path; not reproducible on a live handle
        finally:
            _KERNEL32.CloseHandle(handle)
        return (creation.dwHighDateTime << 32) | creation.dwLowDateTime

else:  # pragma: win32 no cover

    def process_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except OSError as error:
            if error.errno == ESRCH:
                return False
            if error.errno == EPERM:
                return True
            raise
        return True

    if sys.platform in {"linux", "android"}:  # pragma: linux cover
        from io import FileIO

        # The command name can contain spaces and a closing parenthesis. Count fields after its last parenthesis.
        _STARTTIME_INDEX: Final[int] = 19

        def _read_boot_id() -> int:
            # Start times repeat after reboot. A missing boot ID leaves the token readable by older clients.
            try:
                path: Final[Path] = Path("/proc/sys/kernel/random/boot_id")
                # A file mounted over this procfs path can carry a different ID for the same running kernel.
                if path.stat().st_dev != Path("/proc").stat().st_dev:
                    return 0
                # A bind mount of another procfs file keeps the device ID but has its own mountpoint.
                mountpoint = bytes(path)
                with Path("/proc/self/mountinfo").open("rb") as mounts:
                    if any(line.split(b" ", 5)[4] == mountpoint for line in mounts):
                        return 0
                return int(path.read_text(encoding="ascii").strip().replace("-", ""), 16)
            except (OSError, ValueError):
                return 0

        _BOOT_ID: Final[int] = _read_boot_id()
        #: ``TIME_NS_INIT_INO`` in ``linux/proc_ns.h``, fixed by the kernel ABI like the initial PID namespace's inode.
        _INITIAL_TIME_NAMESPACE: Final[int] = 0xEFFFFFFA

        class _UnshiftedNamespace(FileIO):
            last: _UnshiftedNamespace | None = None

            def __init__(self, path: Path) -> None:
                super().__init__(path, "rb")
                self.identity = os.fstat(self.fileno())

            def __del__(self) -> None:
                # Replacing the cache entry releases its namespace pin.
                self.close()

        def process_start_token(pid: int) -> int | None:
            # A foreign procfs can name another process under the same PID. A time offset shifts its start time.
            return _read_start_token(pid) if _proc_numbers_tasks_as_here() and _starttime_unshifted() else None

        def _proc_numbers_tasks_as_here() -> bool:
            # Mounts and PID namespaces can change after import, so check the procfs on each read.
            own: Final[str] = str(os.getpid())
            try:
                # The link names this process by the procfs's namespace, and dangles where that one cannot see it.
                if str(Path("/proc/self").readlink()) != own:
                    return False
                status: Final[bytes] = Path("/proc/self/status").read_bytes()
            except OSError:
                return False
            # Multiple NSpid fields reveal an outer procfs even when the PIDs coincide. Older kernels omit NSpid.
            return all(
                line.split() == [b"NSpid:", own.encode()] for line in status.split(b"\n") if line.startswith(b"NSpid:")
            )

        def _starttime_unshifted() -> bool:
            # setns can move this process into another time namespace, so ask on every read.
            # /proc/self names the group leader, which may have exited while another thread still holds a lock.
            try:
                namespace_path = Path("/proc/thread-self/ns/time")
                namespace = namespace_path.stat()
            except FileNotFoundError:  # no entry means no time namespaces on this kernel
                return True
            except OSError:  # any other failure leaves the namespace unknown, so starttime is not comparable
                return False
            if namespace.st_ino == _INITIAL_TIME_NAMESPACE or (
                (cached := _UnshiftedNamespace.last) is not None and os.path.samestat(namespace, cached.identity)
            ):
                return True
            # Read the worker's offsets through its TID if it outlives the group leader.
            try:
                pin = _UnshiftedNamespace(namespace_path)
            except OSError:
                pin = None
            try:
                if not os.path.samestat(Path("/proc/thread-self/ns/time_for_children").stat(), namespace):
                    return False
                tid = Path("/proc/thread-self").readlink().name
                offsets: Final[str] = Path(f"/proc/{tid}/timens_offsets").read_text(encoding="ascii")
            except OSError:
                return False
            # The clock goes by name since Linux 5.8 and by clock id before.
            unshifted = any(line.split() in (["boottime", "0", "0"], ["7", "0", "0"]) for line in offsets.splitlines())
            # An entered namespace has immutable offsets. Keep one namespace alive so inode reuse cannot match it.
            if unshifted and pin is not None and os.path.samestat(namespace, pin.identity):
                _UnshiftedNamespace.last = pin
            return unshifted

        def _read_start_token(pid: int) -> int | None:
            try:
                data = Path(f"/proc/{pid}/stat").read_bytes()
            except OSError:
                return None
            fields = data[data.rfind(b")") + 1 :].split()
            if len(fields) <= _STARTTIME_INDEX:
                return None
            try:
                starttime = int(fields[_STARTTIME_INDEX])
            except ValueError:
                return None
            return (_BOOT_ID << 64) | starttime

        def _owner_runs_elsewhere(pid: int, start_token: int | None) -> bool:
            # Older markers lack a PID namespace. An owner in another namespace can still hold the lock.
            if start_token is None or (_BOOT_ID and start_token >> 64 not in {0, _BOOT_ID}):
                return False
            unshifted: Final[bool] = _starttime_unshifted()
            try:
                with os.scandir("/proc") as entries:
                    return any(
                        entry.name.isdigit()
                        and (task := int(entry.name)) != pid
                        and (
                            not unshifted
                            or ((token := _read_start_token(task)) is not None and _same_start(token, start_token))
                        )
                        and _innermost_pid(task) == pid
                        for entry in entries
                    )
            except OSError:
                # An unreadable procfs leaves the legacy PID check as the only evidence.
                return False

        def _innermost_pid(task: int) -> int | None:
            try:
                status: Final[bytes] = Path(f"/proc/{task}/status").read_bytes()
            except OSError:  # pragma: no cover  # the task exited between the stat read and this one
                return None
            # Only a newline terminates a procfs status field. Task names can contain other line separators.
            return next(
                (int(line.split()[-1]) for line in status.split(b"\n") if line.startswith(b"NSpid:")),
                None,  # kernels before 4.1 record no namespace PIDs
            )

    elif sys.platform == "darwin":  # pragma: darwin cover
        import ctypes
        import struct

        _LIBC: Final[ctypes.CDLL] = ctypes.CDLL(None, use_errno=True)
        _CTL_KERN: Final[int] = 1
        _KERN_PROC: Final[int] = 14
        _KERN_PROC_PID: Final[int] = 1
        # The kernel kinfo_proc ABI stores the start time in its first timeval.
        _TIMEVAL_AT_ZERO: Final[str] = "<qi"
        _TIMEVAL_SIZE: Final[int] = struct.calcsize(_TIMEVAL_AT_ZERO)

        def process_start_token(pid: int) -> int | None:
            mib = (ctypes.c_int * 4)(_CTL_KERN, _KERN_PROC, _KERN_PROC_PID, pid)
            length = ctypes.c_size_t(0)
            # A dead PID can pass the size probe and return zero bytes on the second call.
            if _LIBC.sysctl(mib, 4, None, ctypes.byref(length), None, 0) != 0:
                return None
            buffer = (ctypes.c_char * length.value)()
            if _LIBC.sysctl(mib, 4, buffer, ctypes.byref(length), None, 0) != 0 or length.value < _TIMEVAL_SIZE:
                return None
            seconds, microseconds = struct.unpack_from(_TIMEVAL_AT_ZERO, buffer.raw, 0)
            return seconds * 1_000_000 + microseconds

    else:  # pragma: no cover  # a POSIX platform without a proven start-time source falls back to fail-closed liveness

        def process_start_token(pid: int) -> int | None:
            del pid
            return None


if sys.platform not in {"linux", "android"}:  # pragma: linux no cover  # pragma: android no cover

    def _owner_runs_elsewhere(pid: int, start_token: int | None) -> bool:
        # Without Linux PID namespaces, a PID that is gone or recycled leaves its owner nowhere else to run.
        del pid, start_token
        return False


def link_host() -> str | None:  # pragma: needs posix-hard-link
    if sys.platform in {"linux", "android"}:  # pragma: darwin no cover
        try:
            Path("/proc/self/ns/pid").stat()
        except OSError:
            # An unreadable procfs gives different PID namespaces the same hostname; none can prove a peer dead.
            return None
        if not _proc_numbers_tasks_as_here():
            return None
    return host_name()


__all__ = [
    "link_host",
    "owner_is_current_process",
    "owner_is_stale",
    "process_alive",
    "process_start_token",
]
