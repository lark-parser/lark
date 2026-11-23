"""Bootstrap."""

from __future__ import annotations

__lazy_modules__ = [
    "concurrent.futures",
    "functools",
    "pathlib",
    "subprocess",
    "threading",
    "traceback",
    "virtualenv.info",
    "virtualenv.seed.wheels",
    f"{__spec__.parent}.pip_install.copy",  # ty: ignore[missing-union-attribute]  # imported modules have a spec
    f"{__spec__.parent}.pip_install.symlink",  # ty: ignore[missing-union-attribute]  # imported modules have a spec
]

import logging
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from functools import partial
from pathlib import Path
from subprocess import CalledProcessError
from threading import Event, Lock
from typing import TYPE_CHECKING, Final

from virtualenv.info import fs_supports_symlink
from virtualenv.seed.embed.base_embed import BaseEmbed
from virtualenv.seed.wheels import get_wheel

from .pip_install.copy import CopyPipInstall
from .pip_install.symlink import SymlinkPipInstall

if TYPE_CHECKING:
    from argparse import ArgumentParser
    from collections.abc import Callable, Generator, Iterable
    from typing import NoReturn

    from python_discovery import PythonInfo

    from virtualenv.app_data.base import AppData
    from virtualenv.config.cli.parser import VirtualEnvOptions
    from virtualenv.create.creator import Creator
    from virtualenv.seed.wheels.util import Wheel
    from virtualenv.util.lock import PathLockBase

    from .pip_install.base import PipInstall

LOGGER: Final[logging.Logger] = logging.getLogger(__name__)  # simplint: ignore[module-variable-prefix]  # existing name


class FromAppData(BaseEmbed):
    """Seeder that installs the seed packages from wheel images cached in the application data folder.

    :param options: the parsed options

    :var symlinks: ``True`` to symlink the packages from the cached images instead of copying them

    """

    def __init__(self, options: VirtualEnvOptions) -> None:
        super().__init__(options)
        self._exit_on_interrupt: Callable[[int], NoReturn] | None = getattr(options, "exit_on_seed_interrupt", None)
        # env var and config file values skip the gate on the CLI flag, so apply it here too
        self.symlinks = options.symlink_app_data and self._can_symlink(self.app_data)
        if options.symlink_app_data and self.app_data.transient:
            LOGGER.debug("copy seed packages because temporary app-data is removed after creation")
        elif options.symlink_app_data and not self.symlinks:
            LOGGER.debug("copy seed packages because the filesystem does not support symlinks")

    @staticmethod
    def _can_symlink(app_data: AppData) -> bool:
        return app_data.transient is False and fs_supports_symlink()

    def __repr__(self) -> str:
        msg = f", via={'symlink' if self.symlinks else 'copy'}, app_data_dir={self.app_data}"
        base = super().__repr__()
        return f"{base[:-1]}{msg}{base[-1]}"

    @classmethod
    def add_parser_arguments(cls, parser: ArgumentParser, interpreter: PythonInfo, app_data: AppData) -> None:
        """Add the option that symlinks the packages from the application data folder, when the platform supports it.

        :param parser: the parser to add the option to
        :param interpreter: the interpreter the environment is created from
        :param app_data: the application data folder

        """
        super().add_parser_arguments(parser, interpreter, app_data)
        can_symlink = cls._can_symlink(app_data)
        sym = "" if can_symlink else "not supported - "
        parser.add_argument(
            "--symlink-app-data",
            dest="symlink_app_data",
            action="store_true" if can_symlink else "store_false",
            help=f"{sym} symlink the python packages from the app-data folder (requires seed pip>=19.3)",
            default=False,
        )

    def run(self, creator: Creator) -> None:
        """Install the seed packages into the environment from the cached images.

        :param creator: the creator of the environment

        :raises RuntimeError: when an image cannot be built, a wheel entry is invalid or a download fails

        """
        if not self.enabled:
            return
        with self._get_seed_wheels(creator) as name_to_whl:
            installer_class = self.installer_class(name_to_whl["pip"].version_tuple if "pip" in name_to_whl else None)
            exceptions = {}
            install_lock: Final[Lock] = Lock()

            def _install(name: str, wheel: Wheel) -> None:
                LOGGER.debug("install %s from wheel %s via %s", name, wheel, installer_class.__name__)
                try:
                    wheel_img = self.app_data.wheel_image(
                        creator.interpreter.version_release_str, Path(installer_class.__name__) / wheel.sha256
                    )
                    installer = installer_class(wheel.path, creator, wheel_img)
                    _build_wheel_image(self.app_data.lock / wheel_img.parent, wheel_img.name, installer)
                    with install_lock:
                        # version_info is a VersionInfo, which install types as a plain tuple
                        installer.install(creator.interpreter.version_info)  # ty: ignore[invalid-argument-type]
                # the failure is stored and raised once every install has finished
                except Exception:  # ruff:ignore[blind-except]
                    exceptions[name] = sys.exc_info()

            self._run_workers(partial(_install, name, wheel) for name, wheel in name_to_whl.items())
            if exceptions:
                messages = [f"failed to build image {', '.join(exceptions.keys())} because:"]
                for value in exceptions.values():
                    exc_type, exc_value, exc_traceback = value
                    messages.append("".join(traceback.format_exception(exc_type, exc_value, exc_traceback)))
                raise RuntimeError("\n".join(messages))

    @contextmanager
    # the wheel lookup and its image build share one context, splitting it passes the lock around
    def _get_seed_wheels(self, creator: Creator) -> Generator[dict[str, Wheel], None, None]:
        name_to_whl, lock, fail = {}, Lock(), {}

        def _get(distribution: str, version: str | None) -> None:
            for_py_version = creator.interpreter.version_release_str
            failure, result = None, None
            # fallback to download in case the exact version is not available
            for download in [True] if self.download else [False, True]:
                failure = None
                try:
                    result = get_wheel(
                        distribution=distribution,
                        version=version,
                        for_py_version=for_py_version,
                        search_dirs=self.extra_search_dir,
                        download=download,
                        app_data=self.app_data,
                        do_periodic_update=self.periodic_update,
                        env=self.env,
                    )
                    if result is not None:
                        break
                except Exception as exception:
                    LOGGER.exception("fail")
                    failure = exception
            if failure:
                if isinstance(failure, CalledProcessError):
                    msg = f"failed to download {distribution}"
                    if version is not None:
                        msg += f" version {version}"
                    msg += f", pip download exit code {failure.returncode}"
                    if output := failure.output + failure.stderr:
                        msg += "\n"
                        msg += output
                else:
                    msg = repr(failure)
                LOGGER.error(msg)
                with lock:
                    fail[distribution] = version
            else:
                with lock:
                    name_to_whl[distribution] = result

        self._run_workers(
            partial(_get, distribution, version) for distribution, version in self.distribution_to_versions().items()
        )
        if fail:
            msg = f"seed failed due to failing to download wheels {', '.join(fail.keys())}"
            raise RuntimeError(msg)
        yield name_to_whl

    def installer_class(self, pip_version_tuple: tuple[int, ...] | None) -> type[PipInstall]:
        """Return the installer class for the pip version, which symlinks the files when pip supports it.

        :param pip_version_tuple: the version of the seed pip, ``None`` when unknown

        :returns: the symlink installer when symlinks are requested and supported, otherwise the copy installer

        """
        if self.symlinks and pip_version_tuple and pip_version_tuple >= (19, 3):  # symlink support requires pip 19.3+
            return SymlinkPipInstall
        return CopyPipInstall

    def _run_workers(self, work: Iterable[Callable[[], None]]) -> None:
        with ThreadPoolExecutor() as executor:
            workers: list[_SeedWorker] = []
            try:
                for task in work:
                    worker = _SeedWorker(task)
                    workers.append(worker)
                    _submit_or_run(executor, worker)
                for worker in workers:
                    worker.wait()
            except KeyboardInterrupt:
                self._cancel_workers(workers)
                raise
            for worker in workers:
                if worker.error is not None:
                    raise worker.error

    def _cancel_workers(self, workers: list[_SeedWorker]) -> None:
        while True:
            try:
                for worker in workers:
                    worker.skip()
                if self._exit_on_interrupt is not None:
                    LOGGER.warning("waiting for seed workers. Press Ctrl+C again to exit immediately")
                for worker in workers:
                    worker.wait()
                break
            except KeyboardInterrupt:
                if self._exit_on_interrupt is not None:
                    # A normal exit would wait for the executor again at interpreter shutdown.
                    self._exit_on_interrupt(130)


def _build_wheel_image(parent: PathLockBase, name: str, installer: PipInstall) -> None:
    with parent.non_reentrant_lock_for_key(name):
        if not installer.has_image():
            installer.build_image()


class _SeedWorker:
    def __init__(self, work: Callable[[], None]) -> None:
        self.work = work
        self.done = Event()
        self.error: BaseException | None = None
        self._lock = Lock()
        self._started = False

    def __call__(self) -> None:
        with self._lock:
            if self._started or self.done.is_set():
                return
            self._started = True
        try:
            self.work()
        except BaseException as exception:
            self.error = exception
            raise
        finally:
            self.done.set()

    def skip(self) -> None:
        with self._lock:
            if not self._started:
                self.done.set()

    def wait(self) -> None:
        # Windows before Python 3.14 cannot interrupt an unbounded lock wait.
        while not self.done.wait(timeout=0.25):
            pass


def _submit_or_run(executor: ThreadPoolExecutor, worker: _SeedWorker) -> None:
    try:
        executor.submit(worker)
    except RuntimeError:
        worker()


__all__ = [
    "FromAppData",
]
