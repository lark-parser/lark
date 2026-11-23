"""Errors."""

from __future__ import annotations


class ProcessCallFailedError(RuntimeError):
    """Failed a process call.

    :param code: the exit code of the process
    :param out: the standard output of the process
    :param err: the standard error of the process
    :param cmd: the command line that was run

    """

    def __init__(self, code: int, out: str, err: str, cmd: list[str]) -> None:
        super().__init__(code, out, err, cmd)
        self.code = code
        self.out = out
        self.err = err
        self.cmd = cmd


__all__ = [
    "ProcessCallFailedError",
]
