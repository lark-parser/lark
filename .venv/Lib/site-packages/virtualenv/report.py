from __future__ import annotations

__lazy_modules__ = ["typing"]

import logging
import sys
from typing import Final

#: Maps each ``-v`` count to the logging level it selects.
LEVELS: Final[dict[int, int]] = {
    0: logging.CRITICAL,
    1: logging.ERROR,
    2: logging.WARNING,
    3: logging.INFO,
    4: logging.DEBUG,
    5: logging.NOTSET,
}

#: The highest ``-v`` count that selects a logging level.
MAX_LEVEL: Final[int] = max(LEVELS.keys())
#: Logger of this module.
LOGGER: Final[logging.Logger] = logging.getLogger()  # simplint: ignore[module-variable-prefix]  # existing name


# show_pid keeps its default for the existing setup_report callers
def setup_report(verbosity: int, show_pid: bool = False) -> int:  # ruff:ignore[boolean-default-value-positional-argument]
    """Configure the root logger to print messages on stdout at the level the verbosity selects.

    :param verbosity: the number of ``-v`` flags, capped at the highest level
    :param show_pid: ``True`` to prefix every message with the process id

    :returns: the verbosity, capped at the highest level

    """
    for log_handler in list(LOGGER.handlers):  # remove handlers of libraries
        LOGGER.removeHandler(log_handler)
    verbosity = min(verbosity, MAX_LEVEL)
    level = LEVELS[verbosity]
    msg_format = "%(message)s"
    if level <= logging.DEBUG:
        msg_format = f"%(relativeCreated)d {msg_format} [%(levelname)s %({'module'})s:%(lineno)d]"
    if show_pid:
        msg_format = f"[%(process)d] {msg_format}"
    formatter = logging.Formatter(msg_format)
    stream_handler = logging.StreamHandler(stream=sys.stdout)
    stream_handler.setLevel(level)
    LOGGER.setLevel(logging.NOTSET)
    stream_handler.setFormatter(formatter)
    LOGGER.addHandler(stream_handler)
    LOGGER.debug("setup logging to %s", logging.getLevelName(level))
    logging.getLogger("distlib").setLevel(logging.ERROR)
    return verbosity


__all__ = [
    "LEVELS",
    "MAX_LEVEL",
    "setup_report",
]
