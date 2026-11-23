"""Lock state and descriptor ownership across a process fork."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    assert __spec__ is not None

__lazy_modules__ = [
    "functools",
    "pathlib",
    f"{__spec__.parent}._registry",
    f"{__spec__.parent}._settings",
    f"{__spec__.parent}._shutdown",
]

import contextlib
import os
import pathlib
import sys
from abc import abstractmethod
from contextlib import contextmanager
from dataclasses import dataclass
from functools import partial
from itertools import count, starmap
from threading import Condition, RLock, get_ident
from typing import Final
from weakref import WeakValueDictionary

from ._registry import REGISTRY
from ._settings import CONSTRUCTOR_SIGNATURES
from ._shutdown import interpreter_exiting

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

    from _typeshed import Unused  # simplint: ignore[private-import-path]  # precise audit callback type


class ForkResettable:
    __slots__ = ()

    @abstractmethod
    def _reset_after_fork_in_child(self) -> None: ...


class ForkDescriptorOwner:
    __slots__ = ()

    @abstractmethod
    def _descriptors_for_fork(self) -> tuple[tuple[int, tuple[int, int] | None], ...]: ...


class ForkClassResettable:
    __slots__ = ()

    @classmethod
    @abstractmethod
    def _reset_class_after_fork(cls) -> None: ...


HAS_REGISTER_AT_FORK: Final[bool] = getattr(os, "register_at_fork", None) is not None


def register_fork_class(cls: type[ForkClassResettable]) -> None:
    if not HAS_REGISTER_AT_FORK:
        return  # pragma: lacks fork
    with fork_transition(), _FORK_STATE.registry_lock:  # pragma: needs fork
        _FORK_CLASSES[id(cls)] = cls
        _refresh_owner_pins()


@contextmanager
def fork_transition(descriptor_owner: ForkDescriptorOwner | None = None) -> Generator[None]:
    # A daemon may hold the gate through shutdown. The exiting thread must still be able to release its locks.
    if not HAS_REGISTER_AT_FORK or interpreter_exiting():
        yield  # pragma: lacks fork
        return  # pragma: lacks fork
    ensure_current_process()  # pragma: needs fork
    creator_pid = os.getpid()  # pragma: needs fork
    # The generator may be finalized outside the thread that entered the transition.
    thread_id: Final[int] = get_ident()  # pragma: needs fork
    with _FORK_STATE.gate:  # pragma: needs fork
        while (
            _FORK_STATE.admission_closed
            and thread_id not in _FORK_STATE.fork_owner_depths
            and thread_id not in _FORK_STATE.transitions
        ):
            _FORK_STATE.gate.wait()  # pragma: no cover - exercised in isolated interpreter
        token: Final[int] = next(_TRANSITION_TOKENS)
        _FORK_STATE.transitions.setdefault(thread_id, {})[token] = descriptor_owner
        _FORK_STATE.active_transitions += 1
    try:  # pragma: needs fork
        yield
    finally:
        if os.getpid() == creator_pid:  # pragma: needs fork
            with _FORK_STATE.gate:
                owned: Final[dict[int, ForkDescriptorOwner | None]] = _FORK_STATE.transitions[thread_id]
                del owned[token]
                if not owned:
                    del _FORK_STATE.transitions[thread_id]
                _FORK_STATE.active_transitions -= 1
                _FORK_STATE.gate.notify_all()


def _refresh_owner_pins() -> None:  # pragma: needs fork
    with _FORK_STATE.gate:
        fork_owner_thread_ids = tuple(_FORK_STATE.fork_owner_depths)
    if get_ident() not in fork_owner_thread_ids:  # pragma: no cover - at-fork callbacks disable tracing
        return
    objects = tuple(_FORK_OBJECTS.values())
    classes = tuple(_FORK_CLASSES.values())
    for thread_id in fork_owner_thread_ids:
        if object_snapshots := _FORK_STATE.pinned_objects.get(thread_id):  # pragma: needs fork
            object_snapshots[:] = [objects] * len(object_snapshots)
            _FORK_STATE.pinned_classes[thread_id][:] = [classes] * len(object_snapshots)


def register_fork_object(instance: ForkResettable) -> None:
    if not HAS_REGISTER_AT_FORK:
        return  # pragma: lacks fork
    with fork_transition(), _FORK_STATE.registry_lock:  # pragma: needs fork
        _FORK_OBJECTS[id(instance)] = instance
        _refresh_owner_pins()


def unregister_owned_descriptor(token: int) -> None:  # pragma: needs fork
    # A daemon may hold the registry lock through shutdown.
    if interpreter_exiting():  # pragma: no cover  # only exit reaches it, after coverage stops measuring
        return
    with fork_transition(), _FORK_STATE.registry_lock:
        _OWNED_DESCRIPTORS.pop(token, None)


def register_owned_descriptor(fd: int, identity: tuple[int, int] | None) -> int | None:
    if not HAS_REGISTER_AT_FORK:
        return None  # pragma: lacks fork
    with fork_transition():  # pragma: needs fork
        if identity is None:
            stat_result = os.fstat(fd)
            identity = stat_result.st_dev, stat_result.st_ino
        return record_owned_descriptor(fd, identity)


@dataclass(frozen=True, slots=True, kw_only=True)
class _OwnedDescriptor:
    fd: int
    creator_pid: int
    device: int | None
    inode: int | None


def _pid_namespace() -> tuple[int, int] | None:
    if sys.platform not in {"linux", "android"}:  # pragma: linux no cover  # pragma: android no cover
        return None
    try:
        namespace = pathlib.Path("/proc/self/ns/pid").stat()
    except OSError:
        return None
    return namespace.st_dev, namespace.st_ino


class _ForkState:
    def __init__(self) -> None:
        self.undrained_forks: set[int] = set()
        self.process_identity = os.getpid(), _pid_namespace()
        self.reset_synchronization()

    def reset_synchronization(self) -> None:
        # A child cannot release locks acquired by threads that stayed in the parent.
        self.gate = Condition(RLock())
        self.registry_lock = RLock()
        self.transitions: dict[int, dict[int, ForkDescriptorOwner | None]] = {}
        self.active_transitions = 0
        self.admission_closed = False
        self.fork_owner_depths: dict[int, int] = {}
        self.pinned_objects: dict[int, list[tuple[ForkResettable, ...]]] = {}
        self.pinned_classes: dict[int, list[tuple[type[ForkClassResettable], ...]]] = {}
        self.provisional_descriptor_tokens: dict[int, list[tuple[int, ...]]] = {}


_FORK_OBJECTS: Final[WeakValueDictionary[int, ForkResettable]] = WeakValueDictionary()
_FORK_CLASSES: Final[WeakValueDictionary[int, type[ForkClassResettable]]] = WeakValueDictionary()
_OWNED_DESCRIPTORS: Final[dict[int, _OwnedDescriptor]] = {}
_DESCRIPTOR_TOKENS: Final[count[int]] = count()
_TRANSITION_TOKENS: Final[count[int]] = count()
_FORK_STATE: Final[_ForkState] = _ForkState()
# A transition still open after this long has an owner that cannot finish it, so it must not hold every fork back.
_FORK_DRAIN_TIMEOUT: Final[float] = 30.0


def _register_fork_hooks() -> None:
    if (register := getattr(os, "register_at_fork", None)) is None:
        return  # pragma: lacks fork
    # Older CPython cannot start tracing another thread while a Python audit hook runs.
    if (  # pragma: needs fork  # pragma: needs settrace-safe-audit-hooks
        sys.implementation.name != "cpython" or sys.version_info >= (3, 12)
    ):
        sys.addaudithook(_audit_fork_safety)
    register(  # pragma: needs fork
        before=_pin_fork_objects,
        after_in_parent=_resume_parent_after_fork,
        after_in_child=partial(ensure_current_process, from_hook=True),
    )


def record_owned_descriptor(fd: int, identity: tuple[int, int] | None) -> int:  # pragma: needs fork
    with _FORK_STATE.registry_lock:
        token = next(_DESCRIPTOR_TOKENS)
        _OWNED_DESCRIPTORS[token] = _OwnedDescriptor(
            fd=fd,
            creator_pid=os.getpid(),
            device=None if identity is None else identity[0],
            inode=None if identity is None else identity[1],
        )
    return token


def _pin_fork_objects() -> None:  # pragma: needs fork
    ensure_current_process()
    thread_id = get_ident()
    provisional_descriptor_tokens: list[int] = []
    # A fork proceeds even when a signal interrupts this hook. Its after-hooks still need a snapshot.
    try:
        with _FORK_STATE.gate:
            _FORK_STATE.fork_owner_depths[thread_id] = _FORK_STATE.fork_owner_depths.get(thread_id, 0) + 1
            _FORK_STATE.admission_closed = True
            if not _FORK_STATE.gate.wait_for(
                lambda: _FORK_STATE.active_transitions <= len(_FORK_STATE.transitions.get(thread_id, ())),
                timeout=_FORK_DRAIN_TIMEOUT,
            ):
                _FORK_STATE.undrained_forks.add(thread_id)
            transition_owners = tuple(_FORK_STATE.transitions.get(thread_id, {}).values())
        with _FORK_STATE.registry_lock:
            for token, descriptor in tuple(_OWNED_DESCRIPTORS.items()):
                if descriptor.creator_pid != os.getpid() or descriptor.device is not None:
                    continue
                try:
                    stat_result = os.fstat(descriptor.fd)
                except OSError:
                    continue
                _OWNED_DESCRIPTORS[token] = _OwnedDescriptor(
                    fd=descriptor.fd,
                    creator_pid=descriptor.creator_pid,
                    device=stat_result.st_dev,
                    inode=stat_result.st_ino,
                )
        for owner in {id(owner): owner for owner in transition_owners if owner is not None}.values():
            descriptors = owner._descriptors_for_fork()  # ruff:ignore[private-member-access]  # fork hook contract
            provisional_descriptor_tokens.extend(starmap(_snapshot_descriptor_for_fork, descriptors))
    finally:
        with _FORK_STATE.registry_lock:
            _FORK_STATE.provisional_descriptor_tokens.setdefault(thread_id, []).append(
                tuple(provisional_descriptor_tokens)
            )
            _FORK_STATE.pinned_objects.setdefault(thread_id, []).append(tuple(_FORK_OBJECTS.values()))
            _FORK_STATE.pinned_classes.setdefault(thread_id, []).append(tuple(_FORK_CLASSES.values()))


def _resume_parent_after_fork() -> None:  # pragma: needs fork
    thread_id = get_ident()
    try:
        with _FORK_STATE.registry_lock:
            for token in _FORK_STATE.provisional_descriptor_tokens[thread_id].pop():
                _OWNED_DESCRIPTORS.pop(token, None)
            _FORK_STATE.pinned_objects[thread_id].pop()
            _FORK_STATE.pinned_classes[thread_id].pop()
            if not _FORK_STATE.provisional_descriptor_tokens[thread_id]:  # pragma: needs fork
                del _FORK_STATE.provisional_descriptor_tokens[thread_id]
                del _FORK_STATE.pinned_objects[thread_id]
                del _FORK_STATE.pinned_classes[thread_id]
    finally:
        # Other threads cannot resume until this hook reopens admission.
        with _FORK_STATE.gate:
            # A handler that raised before the depth was stored left no entry to decrement.
            if (depth := _FORK_STATE.fork_owner_depths.get(thread_id, 1)) <= 1:
                _FORK_STATE.fork_owner_depths.pop(thread_id, None)
            else:  # pragma: no cover - earlier at-fork callbacks may deadlock first
                _FORK_STATE.fork_owner_depths[thread_id] = depth - 1
            _FORK_STATE.admission_closed = bool(_FORK_STATE.fork_owner_depths)
            _FORK_STATE.undrained_forks.discard(thread_id)
            _FORK_STATE.gate.notify_all()


def ensure_current_process(*, from_hook: bool = False) -> None:  # pragma: forked child
    pid = os.getpid()
    thread_id = get_ident()
    if pid == _FORK_STATE.process_identity[0]:
        if thread_id not in _FORK_STATE.fork_owner_depths:
            return
        if not from_hook:
            previous = _FORK_STATE.process_identity[1]
            if previous is None or (current := _pid_namespace()) is None or current == previous:
                return
    if thread_id in _FORK_STATE.undrained_forks:
        os.write(2, b"filelock: fork child exits: another thread was still changing a lock's descriptor ownership\n")
        os._exit(70)  # the inherited descriptor state is unsafe; the parent continues
    pinned_objects = _FORK_STATE.pinned_objects.get(thread_id, [()])[-1]
    pinned_classes = _FORK_STATE.pinned_classes.get(thread_id, [()])[-1]
    descriptors = list(_OWNED_DESCRIPTORS.values())
    _OWNED_DESCRIPTORS.clear()
    _FORK_STATE.reset_synchronization()
    CONSTRUCTOR_SIGNATURES.clear()
    _FORK_STATE.process_identity = pid, _pid_namespace()
    _detach_child_state(descriptors, pinned_objects, pinned_classes)


def _snapshot_descriptor_for_fork(fd: int, identity: tuple[int, int] | None) -> int:  # pragma: needs fork
    if identity is None:  # pragma: needs fork
        try:
            stat_result = os.fstat(fd)
        except OSError:
            pass
        else:
            identity = stat_result.st_dev, stat_result.st_ino
    return record_owned_descriptor(fd, identity)


def _detach_child_state(  # pragma: forked child
    descriptors: list[_OwnedDescriptor],
    pinned_objects: tuple[ForkResettable, ...],
    pinned_classes: tuple[type[ForkClassResettable], ...],
) -> None:
    for descriptor in descriptors:
        if descriptor.device is None:
            continue
        try:
            stat_result = os.fstat(descriptor.fd)
        except OSError:
            continue
        if (stat_result.st_dev, stat_result.st_ino) != (descriptor.device, descriptor.inode):
            continue
        with contextlib.suppress(OSError):
            os.close(descriptor.fd)
    for instance in pinned_objects:
        instance._reset_after_fork_in_child()  # ruff:ignore[private-member-access]  # fork hook contract
    for cls in pinned_classes:
        cls._reset_class_after_fork()
    REGISTRY.held.clear()


# The audit hook can run after interpreter shutdown clears its module globals.
def _audit_fork_safety(  # pragma: no cover - CPython disables tracing while Python audit hooks run
    event: str,
    _args: Unused,
    *,
    _fork_events: frozenset[str] = frozenset({"os.fork", "os.forkpty"}),
    _state: _ForkState = _FORK_STATE,
    _get_ident: Callable[[], int] = get_ident,
) -> None:
    if event in _fork_events:
        if _get_ident() in _state.transitions or _state.fork_owner_depths:
            msg = f"{event} is unsafe while filelock is changing descriptor ownership"
            raise RuntimeError(msg)
    elif event == "_posixsubprocess.fork_exec" and _get_ident() in _state.transitions:
        msg = "fork_exec is unsafe while filelock is changing descriptor ownership"
        raise RuntimeError(msg)


_register_fork_hooks()


__all__ = [
    "HAS_REGISTER_AT_FORK",
    "ForkClassResettable",
    "ForkDescriptorOwner",
    "ForkResettable",
    "ensure_current_process",
    "fork_transition",
    "record_owned_descriptor",
    "register_fork_class",
    "register_fork_object",
    "register_owned_descriptor",
    "unregister_owned_descriptor",
]
