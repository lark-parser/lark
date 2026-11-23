"""Inspect a target Python interpreter virtual environment wise."""

from __future__ import annotations

import sys  # built-in


def encode_path(
    value: object,  # simplint: ignore[imprecise-annotation]  # encodes any value the interpreter reports
) -> str | None:
    """Encode a value for the JSON debug report, turning types and bytes into strings.

    :param value: the value to encode

    :returns: the encoded value, ``None`` for ``None``

    """
    if value is None:
        return None
    if not isinstance(value, (str, bytes)):
        value = repr(value) if isinstance(value, type) else repr(type(value))
    if isinstance(value, bytes):
        value = value.decode(sys.getfilesystemencoding())
    return value


def encode_list_path(
    value: list[object],  # simplint: ignore[imprecise-annotation]  # encodes any value the interpreter reports
) -> list[str | None]:
    """Encode each element of a path list for the JSON debug report.

    :param value: the list of values to encode

    :returns: the encoded values

    """
    return [encode_path(i) for i in value]


def run() -> None:
    """Print debug data about the virtual environment.

    :raises SystemExit: with status 1 when the collected data cannot be encoded as JSON

    """
    sys_info: dict[str, str | list[str | None] | None] = {}
    result: dict[str, str | dict[str, str | list[str | None] | None] | None] = {"sys": sys_info}
    path_keys = (
        "executable",
        "_base_executable",
        "prefix",
        "base_prefix",
        "exec_prefix",
        "base_exec_prefix",
        "path",
        "meta_path",
    )
    for key in path_keys:
        value = getattr(sys, key, None)
        if isinstance(value, list):
            entries = encode_list_path(value)
            # Isolated interpreters and safe-path mode omit the probe directory at startup.
            sys_info[key] = (
                entries[1:] if key == "path" and not getattr(sys.flags, "safe_path", sys.flags.isolated) else entries
            )
        else:
            sys_info[key] = encode_path(value)
    sys_info["fs_encoding"] = sys.getfilesystemencoding()
    sys_info["io_encoding"] = getattr(sys.stdout, "encoding", None)
    result["version"] = sys.version

    try:
        # the script runs in the target interpreter, which may lack sysconfig
        import sysconfig  # ruff:ignore[import-outside-top-level]

        result["makefile_filename"] = encode_path(sysconfig.get_makefile_filename())
    except ImportError:
        pass

    import os  # landmark  # ruff:ignore[import-outside-top-level]

    result["os"] = repr(os)

    try:
        import site  # site  # ruff:ignore[import-outside-top-level]

        result["site"] = repr(site)
    # the target interpreter may lack site, which the probe reports instead of failing
    except ImportError as exception:
        # only a target interpreter without site reaches this branch
        result["site"] = repr(exception)

    try:
        import datetime as dt  # site  # ruff:ignore[import-outside-top-level]

        result["datetime"] = repr(dt)
    # the target interpreter may lack datetime, which the probe reports instead of failing
    except ImportError as exception:
        # only a target interpreter without datetime reaches this branch
        result["datetime"] = repr(exception)

    try:
        import math  # site  # ruff:ignore[import-outside-top-level]

        result["math"] = repr(math)
    # the target interpreter may lack math, which the probe reports instead of failing
    except ImportError as exception:
        # only a target interpreter without math reaches this branch
        result["math"] = repr(exception)

    # try to print out, this will validate if other core modules are available (json in this case)
    try:
        # json is probed on purpose, so a missing core module shows up here
        import json  # ruff:ignore[import-outside-top-level]

        result["json"] = repr(json)
    except ImportError as exception:
        result["json"] = repr(exception)
    else:
        try:
            sys.stdout.write(json.dumps(result, indent=2))
        except (ValueError, TypeError) as exception:
            sys.stderr.write(repr(exception))
            sys.stdout.write(repr(result))
            raise SystemExit(1)  # ruff:ignore[raise-without-from-inside-except]  # exception is reported separately


if __name__ == "__main__":
    run()
