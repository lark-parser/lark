"""Test helpers that keep platformdirs away from the real user and system directories."""

from __future__ import annotations

__lazy_modules__ = [
    "pathlib",
    f"{__spec__.parent}.api",  # ty: ignore[missing-union-attribute]  # imported modules have a spec
]

import os
from contextlib import contextmanager
from pathlib import Path
from threading import RLock

import platformdirs

from .api import PlatformDirsABC

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Generator
    from typing import Final


@contextmanager
def isolated_dirs(root: str | os.PathLike[str]) -> Generator[Path, None, None]:
    """Resolve every directory of :data:`~platformdirs.PlatformDirs` under ``root`` while the context is active.

    Each kind maps to ``<root>/<kind>``, where ``kind`` is the property name without ``_dir``, such as ``user_config``.
    The data, config, cache, state, log, runtime and preference kinds append ``appname`` and ``version``, so
    ``PlatformDirs("app", version="1.0").user_config_path`` becomes ``<root>/user_config/app/1.0``. Every thread of the
    current process sees the newest active root. Forked children inherit it. Spawned processes start with the original
    paths.

    On Unix, ``use_site_for_root`` is ignored inside the context so user and site directories keep separate kinds. A
    relative ``root`` is made absolute on entry, so changing the working directory does not move the isolation root.

    :param root: directory that holds the redirected directories

    :yields: the absolute isolation root as a :class:`~pathlib.Path`

    """
    app_kinds: Final[frozenset[str]] = frozenset({
        "user_data",
        "site_data",
        "user_config",
        "site_config",
        "user_cache",
        "site_cache",
        "user_state",
        "site_state",
        "user_log",
        "site_log",
        "user_runtime",
        "site_runtime",
        "user_preference",
    })

    base = Path(root).absolute()
    patches = {
        name: _redirect(
            base / (kind := name.removesuffix("_dir")), app=kind in app_kinds, private=kind.startswith("user_")
        )
        for name in PlatformDirsABC.__abstractmethods__
    }
    # The usual site lists, root redirection and XDG runtime checks depend on paths outside the isolation root.
    patches |= {
        name: value
        for name, value in vars(PlatformDirsABC).items()
        if name in {"_use_site", "_find_runtime_files", "_iter_runtime_dirs"}
        or (name.startswith("_site_") and name.endswith("_dirs"))
    }
    with _patch_class(platformdirs.PlatformDirs, patches):
        yield base


def _redirect(path: Path, *, app: bool, private: bool) -> property:
    def resolve(self: PlatformDirsABC) -> str:
        return self._append_app_name_and_version(str(path), private=private) if app else str(path)

    return property(resolve)


@contextmanager
def _patch_class(cls: type[PlatformDirsABC], patches: dict[str, property]) -> Generator[None, None, None]:
    scope = _Isolation()
    with _LOCK:
        # Finalizing an older context during installation must leave the new one in place.
        _ACTIVE.setdefault(cls, []).append(scope)
        try:
            scope.saved.update({name: vars(cls)[name] for name in patches if name in vars(cls)})
            scope.missing = patches.keys() - scope.saved.keys()
            for name, value in patches.items():
                setattr(cls, name, value)
        except BaseException:
            # An interrupt during entry must roll back before another thread acquires the lock.
            scope.close(cls)
            raise
    try:
        yield
    finally:
        with _LOCK:
            scope.close(cls)


class _Isolation:
    def __init__(self) -> None:
        self.saved: dict[str, property] = {}
        self.missing: set[str] = set()
        self.closed = False

    def close(self, cls: type[PlatformDirsABC]) -> None:
        self.closed = True
        stack = _ACTIVE[cls]
        if stack[-1] is not self:
            return
        while stack and stack[-1].closed:
            for name, value in stack[-1].saved.items():
                setattr(cls, name, value)
            for name in stack[-1].missing & vars(cls).keys():
                delattr(cls, name)
            stack.pop()
        if not stack:
            del _ACTIVE[cls]


_ACTIVE: Final[dict[type[PlatformDirsABC], list[_Isolation]]] = {}
_LOCK: Final[RLock] = RLock()

if hasattr(os, "register_at_fork"):
    # A child must inherit a complete redirect when another thread is entering or leaving a context.
    os.register_at_fork(before=_LOCK.acquire, after_in_parent=_LOCK.release, after_in_child=_LOCK.release)


__all__ = [
    "isolated_dirs",
]
