"""Patches that are applied at runtime to the virtual environment."""

from __future__ import annotations

__lazy_modules__ = ["contextlib"]

import contextlib
import os
import sys
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    import types
    from collections.abc import Callable, Sequence
    from functools import partial
    from importlib.machinery import ModuleSpec

_VIRTUALENV_PATCH_FILE: Final[str] = os.path.abspath(__file__)


def patch_dist(dist: types.ModuleType) -> None:
    # distutils reads install options from configuration files, and some would install packages outside of the virtual
    # environment: https://docs.python.org/3.11/install/index.html#distutils-configuration-files
    old_parse_config_files = dist.Distribution.parse_config_files

    # matches the untyped distutils parse_config_files override it replaces
    def parse_config_files(self, *args: object, **kwargs: object) -> object:  # ruff:ignore[missing-type-function-argument]  # simplint: ignore[imprecise-annotation]  # distutils signature
        try:
            result = old_parse_config_files(self, *args, **kwargs)
        except UnicodeDecodeError:
            # Distutils keeps options from files it decoded before the error.
            _filter_install_paths(self.command_options)
            raise
        _filter_install_paths(self.command_options)
        return result

    dist.Distribution.parse_config_files = parse_config_files


def _filter_install_paths(command_options: dict[str, dict[str, tuple[str, str]]]) -> None:
    install: Final[dict[str, tuple[str, str]]] = command_options.setdefault("install", {})
    if "prefix" in install:
        install["prefix"] = _VIRTUALENV_PATCH_FILE, os.path.abspath(sys.prefix)
    destinations: Final[tuple[str, ...]] = (
        "install_lib",
        "install_purelib",
        "install_platlib",
        "install_headers",
        "install_scripts",
        "install_data",
    )
    for key in ("exec_prefix", "install_base", "install_platbase", *destinations):
        install.pop(key, None)
    # A subcommand's install_dir takes precedence over the environment's prefix.
    for command in (*destinations, "install_egg_info"):
        if (options := command_options.get(command)) is not None:
            options.pop("install_dir", None)


# Import hook that patches some modules to ignore configuration values that break package installation in case
# of virtual environments.
_DISTUTILS_PATCH: Final[tuple[str, str]] = "distutils.dist", "setuptools.dist"
# https://docs.python.org/3/library/importlib.html#setting-up-an-importer


class _Finder:
    # A meta path finder that allows patching the imported distutils modules.
    fullname = None

    # lock[0] is threading.Lock(), but initialized lazily to avoid importing threading very early at startup,
    # because there are gevent-based applications that need to be first to import threading by themselves.
    # See https://github.com/pypa/virtualenv/issues/1895 for details.
    lock = []  # ruff:ignore[mutable-class-default]

    # lock is a shared cell mutated on purpose, so every finder sees one lock
    def find_spec(
        self,
        fullname: str,
        path: Sequence[str] | None,
        target: types.ModuleType | None = None,  # ruff:ignore[unused-method-argument]  # the finder protocol passes target
    ) -> ModuleSpec | None:
        # Guard against race conditions during file rewrite by checking if _DISTUTILS_PATCH is defined.
        # This can happen when the file is being overwritten while it's being imported by another process.
        # See https://github.com/pypa/virtualenv/issues/2969 for details.
        try:
            distutils_patch = _DISTUTILS_PATCH
        except NameError:
            return None
        if fullname in distutils_patch and self.fullname is None:
            # initialize lock[0] lazily
            if len(self.lock) == 0:
                # the hook runs during import, so threading loads only when the lock is built
                import threading  # ruff:ignore[import-outside-top-level]

                lock = threading.Lock()
                # there is possibility that two threads T1 and T2 are simultaneously running into find_spec,
                # observing .lock as empty, and further going into hereby initialization. However due to the GIL,
                # list.append() operation is atomic and this way only one of the threads will "win" to put the lock
                # - that every thread will use - into .lock[0].
                # https://docs.python.org/3/faq/library.html#what-kinds-of-global-value-mutation-are-thread-safe
                self.lock.append(lock)

            # the hook runs during import, so functools loads only when a spec is patched
            from functools import partial  # ruff:ignore[import-outside-top-level]

            # the hook runs during import, so importlib.util loads only when a spec is needed
            from importlib.util import find_spec  # ruff:ignore[import-outside-top-level]

            with self.lock[0]:
                self.fullname = fullname
                spec = None
                try:
                    # fullname and path arrive typed as object, find_spec takes str | None
                    spec = find_spec(fullname, path)  # ty: ignore[invalid-argument-type]
                finally:
                    self.fullname = None
                if spec is not None:
                    return self._patch_spec(spec, partial)
        return None

    def _patch_spec(self, spec: ModuleSpec, partial: type[partial]) -> ModuleSpec:
        if (old := getattr(spec.loader, "exec_module", None)) is not None and old is not self.exec_module:
            # a loader with a read-only exec_module is left unpatched on purpose
            try:  # ruff:ignore[suppressible-exception]
                # exec_module is a method on the loader, ty types the assignment as read-only
                spec.loader.exec_module = partial(self.exec_module, old)  # ty: ignore[invalid-assignment]
            except AttributeError:
                pass
        elif sys.version_info < (3, 10):
            # Python 3.9's zipimporter lacks exec_module.
            if (load := getattr(spec.loader, "load_module", None)) is None:
                return spec

            def load_module(name: str) -> types.ModuleType:
                module = load(name)
                _Finder._patch_module(module)
                return module

            with contextlib.suppress(AttributeError):
                spec.loader.load_module = load_module  # ty: ignore[invalid-assignment]  # zipimport loader permits rebinding
        return spec

    @staticmethod
    def exec_module(old: Callable[[types.ModuleType], object], module: types.ModuleType) -> None:
        old(module)
        _Finder._patch_module(module)

    @staticmethod
    def _patch_module(module: types.ModuleType) -> None:
        try:
            distutils_patch = _DISTUTILS_PATCH
        except NameError:
            return
        if module.__name__ in distutils_patch:
            with contextlib.suppress(NameError):
                patch_dist(module)


# A newer interpreter can still load a .pth file retained from a Python 3.9 environment.
if sys.version_info < (3, 10):
    sys.meta_path.insert(0, _Finder())
