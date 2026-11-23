from __future__ import annotations

import errno
import logging
import os
import sys
from time import perf_counter
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import MutableMapping

    from virtualenv.config.cli.parser import VirtualEnvOptions
    from virtualenv.run.session import Session

LOGGER: Final[logging.Logger] = logging.getLogger(__name__)  # simplint: ignore[module-variable-prefix]  # existing API


def _run_as_module() -> None:
    try:
        current: Final[str] = os.getcwd()
    except OSError:
        pass
    else:
        if (
            sys.path
            and sys.path[0] == current
            and not getattr(sys.flags, "safe_path", False)
            and os.path.dirname(os.path.dirname(__file__)) != current
        ):
            del sys.path[0]
    run_with_catch()


def run(
    args: list[str] | None = None, options: VirtualEnvOptions | None = None, env: MutableMapping[str, str] | None = None
) -> None:
    env = os.environ if env is None else env
    start = perf_counter()
    # deferred so importing this entry module stays cheap
    from virtualenv.run import cli_run  # ruff:ignore[import-outside-top-level]

    # deferred with the run import, both load only when the CLI runs
    from virtualenv.util.error import ProcessCallFailedError  # ruff:ignore[import-outside-top-level]

    if args is None:
        args = sys.argv[1:]
    try:
        LOGGER.warning(LogSession(cli_run(args, options, env=env), start))
    except ProcessCallFailedError as exception:
        # the failed command is reported to the user as it was run
        print(f"subprocess call failed for {exception.cmd} with code {exception.code}")  # ruff:ignore[print]
        # the child's stdout is forwarded unchanged, not logged
        print(exception.out, file=sys.stdout, end="")  # ruff:ignore[print]
        # the child's stderr is forwarded unchanged, not logged
        print(exception.err, file=sys.stderr, end="")  # ruff:ignore[print]
        # exit with the failed command's status, without chaining its exception
        raise SystemExit(exception.code)  # ruff:ignore[raise-without-from-inside-except]
    except OSError as exception:
        if exception.errno == errno.EMFILE:
            print(  # ruff:ignore[print]  # the open-files hint is a user-facing message written straight to stderr
                "OSError: [Errno 24] Too many open files. You may need to increase your OS open files limit.\n"
                "  On macOS/Linux, try 'ulimit -n 2048'.\n"
                "  For Windows, this is not a common issue, but you can try to close some applications.",
                file=sys.stderr,
            )
        raise


class LogSession:  # simplint: ignore[unexported-public-name]  # existing import
    def __init__(self, session: Session, start: float) -> None:
        self.session = session
        self.start = start

    def __str__(self) -> str:
        spec = self.session.creator.interpreter.spec
        elapsed = (perf_counter() - self.start) * 1000
        lines = [
            f"created virtual environment {spec} in {elapsed:.0f}ms",
            f"  creator {self.session.creator!s}",
        ]
        if self.session.seeder.enabled:
            lines.append(f"  seeder {self.session.seeder!s}")
            path = self.session.creator.purelib.iterdir()
            packages = sorted("==".join(i.stem.split("-")) for i in path if i.suffix == ".dist-info")
            lines.append(f"    added seed packages: {', '.join(packages)}")

        if self.session.activators:
            lines.append(f"  activators {','.join(i.__class__.__name__ for i in self.session.activators)}")
        return "\n".join(lines)


def run_with_catch(args: list[str] | None = None, env: MutableMapping[str, str] | None = None) -> None:
    # deferred so the parser module loads only for the entry point
    from virtualenv.config.cli.parser import VirtualEnvOptions  # ruff:ignore[import-outside-top-level]

    env = os.environ if env is None else env
    options = VirtualEnvOptions(exit_on_seed_interrupt=os._exit)  # only the CLI owns the process
    try:
        run(args, options, env)
    # any failure is handed to _exit_for_exception, which reports it
    except (KeyboardInterrupt, SystemExit, Exception) as exception:  # ruff:ignore[blind-except]
        try:
            _exit_for_exception(options, exception)
        finally:
            for handler in LOGGER.handlers:  # force flush of log messages before the trace is printed
                handler.flush()


def _exit_for_exception(options: VirtualEnvOptions, exception: BaseException) -> None:
    if getattr(options, "with_traceback", False):
        raise exception
    # sys.exit() without a status exits with 0 too, so SystemExit(None) is a success and not an error to report
    if not (isinstance(exception, SystemExit) and (exception.code is None or exception.code == 0)):
        LOGGER.error("%s: %s", type(exception).__name__, exception)
    sys.exit(exception.code if isinstance(exception, SystemExit) else 1)


if __name__ == "__main__":
    _run_as_module()


__all__ = [
    "run",
    "run_with_catch",
]
