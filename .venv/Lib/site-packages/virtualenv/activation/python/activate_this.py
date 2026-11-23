"""Activate virtualenv for current interpreter:

import runpy runpy.run_path(this_file)

This can be used when you must use an existing Python interpreter, not the virtualenv bin/python.

"""  # ruff:ignore[missing-terminal-punctuation]  # the usage line is code, so the docstring needs no closing sentence

from __future__ import annotations

import os
import site
import sys

# runpy.run_path returns these globals; keep the names emitted by existing activation scripts.
try:
    abs_file = os.path.abspath(__file__)  # simplint: ignore[module-variable-case, module-variable-prefix, undocumented-public-api]  # runpy result  # fmt: skip
except NameError as exc:
    msg = "You must use import runpy; runpy.run_path(this_file)"  # simplint: ignore[undocumented-public-api]  # runpy result
    raise AssertionError(msg) from exc

bin_dir = os.path.dirname(abs_file)  # simplint: ignore[module-variable-case, module-variable-prefix, undocumented-public-api]  # runpy result  # fmt: skip
# __BIN_NAME__ is filled in when the script is written
base = bin_dir[: -len(__BIN_NAME__) - 1]  # ty: ignore[unresolved-reference]  # simplint: ignore[module-variable-case, module-variable-prefix, undocumented-public-api]  # runpy result

if os.pathsep in base:
    _path_error = "environment directory contains the PATH separator"
    raise ValueError(_path_error)
if base.partition("%")[2].startswith(("func", "builtin")):
    _msg = "environment directory contains a shell PATH option"
    raise ValueError(_msg)

# Empty PATH entries search the current directory on POSIX.
os.environ["PATH"] = os.pathsep.join([
    bin_dir,
    *(entry for entry in os.environ.get("PATH", "").split(os.pathsep) if entry),
])
os.environ["VIRTUAL_ENV"] = base  # virtual env is right above bin directory
# __VIRTUAL_PROMPT__ is filled in when the script is written
os.environ["VIRTUAL_ENV_PROMPT"] = __VIRTUAL_PROMPT__ or os.path.basename(base)  # ty: ignore[unresolved-reference]
os.environ.pop("PYTHONHOME", None)

# Set PKG_CONFIG_PATH to include the virtualenv's pkgconfig directory
pkg_config_path = os.path.join(base, "lib", "pkgconfig")  # simplint: ignore[module-variable-case, module-variable-prefix, missing-final, undocumented-public-api]  # runpy result  # fmt: skip
if existing_pkg_config_path := os.environ.get("PKG_CONFIG_PATH", ""):
    os.environ["PKG_CONFIG_PATH"] = os.pathsep.join([pkg_config_path, existing_pkg_config_path])
else:
    os.environ["PKG_CONFIG_PATH"] = pkg_config_path


def _add_libraries() -> None:
    original_paths = sys.path[:]
    lib_paths = list(
        dict.fromkeys(
            os.path.realpath(os.path.join(bin_dir, lib))
            for lib in __LIB_FOLDERS__.split(os.pathsep)  # ty: ignore[unresolved-reference]  # filled in during generation
        )
    )
    stdlib_dir = os.path.dirname(os.path.realpath(os.__file__))
    stdlib_candidates = {
        os.path.normcase(os.path.realpath(path))
        for path in (
            stdlib_dir,
            os.path.join(stdlib_dir, "lib-dynload"),
            os.path.join(
                os.path.dirname(stdlib_dir),
                f"python{sys.version_info.major}{sys.version_info.minor}{'t' if sys.implementation.cache_tag.endswith('t') else ''}.zip",
            ),
            os.path.join(sys.base_prefix, "DLLs"),
        )
    }
    # GraalPy keeps implementation modules outside its Python standard library directory.
    if sys.implementation.name == "graalpy":
        base_dir = os.path.normcase(os.path.realpath(sys.base_prefix)) + os.sep
        stdlib_candidates.update(
            real_path
            for path in original_paths
            if path
            and (real_path := os.path.normcase(os.path.realpath(path))).startswith(base_dir)
            and os.path.basename(real_path) == "modules"
            and os.path.basename(os.path.dirname(real_path)).startswith("graalpy")
        )
    stdlib_paths = [
        path for path in original_paths if path and os.path.normcase(os.path.realpath(path)) in stdlib_candidates
    ]
    # .pth imports need the environment before host paths, with the standard library still first.
    sys.path[:] = (
        stdlib_paths
        + lib_paths
        + [path for path in original_paths if path not in stdlib_paths and path not in lib_paths]
    )
    added_paths = []
    for path in lib_paths:
        if path not in original_paths:
            added_paths.append(path)
        # .pth import lines can insert paths anywhere, including duplicates.
        previous_paths: dict[str, int] = {}
        for entry in sys.path:
            previous_paths[entry] = previous_paths.get(entry, 0) + 1
        # __DECODE_PATH__ is filled in as an empty string, so the decode branch never runs
        site.addsitedir(path.decode("utf-8") if __DECODE_PATH__ else path)  # ty: ignore[unresolved-reference,missing-attribute]
        for entry in sys.path:
            if previous_paths.get(entry):
                previous_paths[entry] -= 1
            else:
                added_paths.append(entry)
    sys.path[:] = added_paths + original_paths


_add_libraries()

# sys.real_prefix is a legacy attribute that older tools read
sys.real_prefix = sys.prefix  # ty: ignore[missing-attribute]
sys.prefix = base
# a venv interpreter has both prefixes at the environment, and on POSIX sysconfig derives the platlib, platstdlib and
# platinclude paths from sys.exec_prefix, so compiled packages pip installs here would otherwise land in the base Python
sys.exec_prefix = base
