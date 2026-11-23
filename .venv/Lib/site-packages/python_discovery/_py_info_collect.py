# simplint: ignore[flattened-package]  # ruff: ignore[commented-out-code]  # keep the existing private path
"""
Collect interpreter information, also run as the subprocess interrogation script (stdlib only).

Executed by the interpreter being probed. Collection supports Python 3.6+, but the file must parse on 2.7 so the
version gate below can report older interpreters instead of dying with a ``SyntaxError``: no f-strings, no walrus
operator, no annotations, no typing imports, no imports from this package. The gate sits above every other import
so that 3.0 and 3.1, which lack ``sysconfig``, still reach it.
"""

import sys

MIN_INTERROGATE_VERSION = (3, 6)
UNSUPPORTED_EXIT_CODE = 79  # first value past the sysexits.h range, so no stdlib or shell meaning
UNSUPPORTED_MARKER = "unsupported Python version "

if __name__ == "__main__" and sys.version_info[:2] < MIN_INTERROGATE_VERSION:  # pragma: no cover # needs <3.6
    sys.stderr.write(
        "{}{}\n{}".format(UNSUPPORTED_MARKER, ".".join(str(i) for i in sys.version_info[:3]), sys.executable)
    )
    raise SystemExit(UNSUPPORTED_EXIT_CODE)

import json
import os
import platform
import re
import struct
import sysconfig
import warnings
from collections import namedtuple

# ruff:ignore[collections-named-tuple] # typing.NamedTuple class syntax needs annotations, unavailable on 3.6
VersionInfo = namedtuple("VersionInfo", ["major", "minor", "micro", "releaselevel", "serial"])

_CONF_VAR_RE = re.compile(
    r"""
    \{ \w+  }   # sysconfig variable placeholder like {base}
    """,
    re.VERBOSE,
)


# Each attribute is a public PythonInfo field and a key of the cached JSON, so they stay flat.
class PythonInfoCollector:  # simplint: ignore[too-many-attributes]
    # Collects information about the currently running Python interpreter.
    def __init__(self):
        self._init_identity()
        self._init_prefixes()
        self._init_schemes()
        self._init_sysconfig()

    def _init_identity(self):
        self.platform = sys.platform
        self.implementation = platform.python_implementation()
        if self.implementation == "GraalVM":
            self.implementation = "GraalPy"
        if self.implementation == "PyPy":
            self.pypy_version_info = tuple(sys.pypy_version_info)  # ty: ignore[unresolved-attribute] # pypy only

        self.version_info = VersionInfo(*sys.version_info)
        # same as stdlib platform.architecture to account for pointer size != max int
        self.architecture = 32 if struct.calcsize("P") < struct.calcsize("Q") else 64
        self.sysconfig_platform = sysconfig.get_platform()
        self.version_nodot = sysconfig.get_config_var("py_version_nodot")
        self.version = sys.version
        self.os = os.name
        self.free_threaded = sysconfig.get_config_var("Py_GIL_DISABLED") == 1
        self.debug_build = bool(sysconfig.get_config_var("Py_DEBUG"))
        # Vermin checks the whole script against Python 2.7 despite the version gate above.
        interpreter = getattr(sys, "implementation")  # ruff:ignore[get-attr-with-constant]
        interpreter_version = interpreter.version
        marker_version = "{}.{}.{}{}".format(
            interpreter_version.major,
            interpreter_version.minor,
            interpreter_version.micro,
            "{}{}".format(interpreter_version.releaselevel[0], interpreter_version.serial)
            if interpreter_version.releaselevel != "final"
            else "",
        )
        self.marker_environment = {
            "implementation_name": interpreter.name,
            "implementation_version": marker_version,
            "os_name": os.name,
            "platform_machine": platform.machine(),
            "platform_release": platform.release(),
            "platform_system": platform.system(),
            "platform_version": platform.version(),
            "python_full_version": platform.python_version(),
            "platform_python_implementation": platform.python_implementation(),
            "python_version": ".".join(platform.python_version_tuple()[:2]),
            "sys_platform": sys.platform,
        }

    def _init_prefixes(self):
        def abs_path(value):
            return None if value is None else os.path.abspath(value)

        self.prefix = abs_path(getattr(sys, "prefix", None))
        self.base_prefix = abs_path(getattr(sys, "base_prefix", None))
        self.real_prefix = abs_path(getattr(sys, "real_prefix", None))
        self.base_exec_prefix = abs_path(getattr(sys, "base_exec_prefix", None))
        self.exec_prefix = abs_path(getattr(sys, "exec_prefix", None))

        self.executable = abs_path(sys.executable)
        self.original_executable = abs_path(self.executable)
        self.system_executable = self._fast_get_system_executable()

        try:
            __import__("venv")
            has = True
        except ImportError:  # pragma: no cover # venv is always available in standard CPython
            has = False
        self.has_venv = has
        self.path = sys.path
        self.file_system_encoding = sys.getfilesystemencoding()
        self.stdout_encoding = getattr(sys.stdout, "encoding", None)

    def _fast_get_system_executable(self):
        # Try to get the system executable by just looking at properties.
        # Preserve the invoked path because shims may rely on it.
        if not (self.real_prefix or (self.base_prefix is not None and self.base_prefix != self.prefix)):
            return self._resolve_executable_symlink(self.original_executable)

        if self.real_prefix is not None:
            return None

        base_executable = getattr(sys, "_base_executable", None)
        if base_executable is None:
            return None

        if sys.executable == base_executable:
            return None

        # CPython accepts pythonX without checking its version when resolving a copied venv.
        if os.path.exists(base_executable):  # pragma: >=3.11 cover
            major = self.version_info.major
            ambiguous_names = {"python", "python{}".format(major)}
            if self.implementation == "PyPy":
                ambiguous_names.update({"pypy", "pypy3", "pypy{}".format(major)})
            if os.path.basename(base_executable) in ambiguous_names:
                versioned = self._try_posix_versioned_executable(base_executable)
                if versioned is not None and not os.path.samefile(base_executable, versioned):
                    base_executable = versioned
            return self._resolve_executable_symlink(base_executable)

        # Try fallback for POSIX virtual environments
        return self._try_posix_fallback_executable(base_executable)  # pragma: >=3.11 cover

    def _resolve_executable_symlink(self, path):
        # Resolve symlinks of the executable itself, but never of its parent directories.
        #
        # Mirrors CPython's ``getpath.realpath`` (and ``venv`` in python/cpython#115237): an executable-only symlink
        # resolves to the real interpreter so its home can be located, while a fully symlinked interpreter tree is
        # kept as-is. Like ``getpath``, resolution stops as soon as the stdlib landmark is reachable from the current
        # directory - an alias such as Debian's ``/usr/bin/python3`` is a usable home and stays untouched.
        result = os.path.abspath(path)
        if self.os != "posix":  # pragma: win32 cover # CPython only does this where HAVE_READLINK
            return result
        if sysconfig.get_config_var("PYTHONFRAMEWORK"):  # macOS framework builds self-locate via dyld; e.g. Homebrew
            return result  # resolving would pin the versioned Cellar path into the recorded home
        real_path = os.path.realpath(result)
        if not os.path.exists(real_path):  # symlink loop or broken symlink
            return result
        while os.path.islink(result):
            if self._stdlib_landmark_exists(os.path.dirname(result)):
                return result
            link = os.readlink(result)
            candidate = link if os.path.isabs(link) else os.path.normpath(os.path.join(os.path.dirname(result), link))
            # normpath through a symlinked directory may point at a different file - stop resolving there
            if not (os.path.exists(candidate) and os.path.samefile(real_path, candidate)):
                return result
            result = candidate
        return result

    @staticmethod
    def _stdlib_landmark_exists(dir_path):
        lib_name = os.path.basename(os.path.dirname(os.__file__))
        return any(
            os.path.exists(os.path.join(dir_path, os.pardir, lib, lib_name, "os.py")) for lib in ("lib", "lib64")
        )

    def _try_posix_versioned_executable(self, base_executable):
        major, minor = self.version_info.major, self.version_info.minor
        if self.os != "posix" or (major, minor) < (3, 11):
            return None

        base_dir = os.path.dirname(base_executable)
        candidates = ["python{}.{}".format(major, minor)]
        if self.implementation == "PyPy":
            candidates.insert(0, "pypy{}.{}".format(major, minor))

        for candidate in candidates:
            full_path = os.path.join(base_dir, candidate)
            if os.path.exists(full_path):
                return full_path

        return None

    def _try_posix_fallback_executable(self, base_executable):
        # Find a versioned Python binary as fallback for POSIX virtual environments.
        versioned = self._try_posix_versioned_executable(base_executable)
        if versioned is not None:
            return versioned

        major, minor = self.version_info.major, self.version_info.minor
        if self.os != "posix" or (major, minor) < (3, 11):
            return None

        base_dir = os.path.dirname(base_executable)
        candidates = ["python{}".format(major)]
        if self.implementation == "PyPy":
            candidates.extend(["pypy", "pypy3", "pypy{}".format(major)])

        for candidate in candidates:
            full_path = os.path.join(base_dir, candidate)
            if os.path.exists(full_path):
                return full_path

        return None

    def _init_schemes(self):
        scheme_names = sysconfig.get_scheme_names()

        if "venv" in scheme_names:  # pragma: >=3.11 cover
            self.sysconfig_scheme = "venv"
            self.sysconfig_paths = {
                i: sysconfig.get_path(i, expand=False, scheme=self.sysconfig_scheme) for i in sysconfig.get_path_names()
            }
            self.distutils_install = {}
        # debian / ubuntu python 3.10 without `python3-distutils` will report mangled `local/bin` / etc. names
        elif sys.version_info[:2] == (3, 10) and "deb_system" in scheme_names:  # pragma: no cover # Debian/Ubuntu 3.10
            self.sysconfig_scheme = "posix_prefix"
            self.sysconfig_paths = {
                i: sysconfig.get_path(i, expand=False, scheme=self.sysconfig_scheme) for i in sysconfig.get_path_names()
            }
            self.distutils_install = {}
        else:  # pragma: no cover # "venv" scheme always present on Python 3.12+
            self.sysconfig_scheme = None
            self.sysconfig_paths = {i: sysconfig.get_path(i, expand=False) for i in sysconfig.get_path_names()}
            self.distutils_install = self._distutils_install().copy()

    @staticmethod
    def _distutils_install():  # pragma: <3.11 cover # 3.11+ uses the "venv" scheme instead
        # use distutils primarily because that's what pip does
        # https://github.com/pypa/pip/blob/main/src/pip/_internal/locations.py#L95
        # Avoid importing Distribution before setuptools can patch it.
        with warnings.catch_warnings():  # disable warning for PEP-632
            warnings.simplefilter("ignore")
            try:
                # ruff:ignore[import-outside-top-level] distutils is optional and removed in newer Pythons
                from distutils import dist  # ty: ignore[unresolved-import] removed in 3.12

                # ruff:ignore[import-outside-top-level] distutils is optional and removed in newer Pythons
                from distutils.command.install import SCHEME_KEYS  # ty: ignore[unresolved-import] removed in 3.12
            except ImportError:  # pragma: no cover # if removed or not installed ignore
                return {}

        distribution = dist.Distribution({
            "script_args": "--no-user-cfg",
        })  # conf files not parsed so they do not hijack paths
        if hasattr(sys, "_framework"):  # pragma: no cover # macOS framework builds only
            sys._framework = None  # ty: ignore[invalid-assignment]  # ruff:ignore[private-member-access] macOS paths

        with warnings.catch_warnings():  # disable warning for PEP-632
            warnings.simplefilter("ignore")
            install = distribution.get_command_obj("install", create=True)

        install.prefix = os.sep  # paths generated are relative to prefix that contains the path sep
        install.finalize_options()
        return {key: (getattr(install, "install_{}".format(key))[1:]).lstrip(os.sep) for key in SCHEME_KEYS}

    def _init_sysconfig(self):
        makefile = getattr(sysconfig, "get_makefile_filename", getattr(sysconfig, "_get_makefile_filename", None))
        self.sysconfig = {
            k: v
            for k, v in [
                ("makefile_filename", makefile() if makefile is not None else None),
            ]
            if k is not None
        }

        config_var_keys = set()
        for element in self.sysconfig_paths.values():
            config_var_keys.update(k[1:-1] for k in _CONF_VAR_RE.findall(element))
        config_var_keys.add("PYTHONFRAMEWORK")
        config_var_keys.update(("Py_ENABLE_SHARED", "INSTSONAME", "LIBDIR"))

        self.sysconfig_vars = {i: sysconfig.get_config_var(i or "") for i in config_var_keys}

        if "TCL_LIBRARY" in os.environ:
            self.tcl_lib, self.tk_lib = self._get_tcl_tk_libs()
        else:
            self.tcl_lib, self.tk_lib = None, None

        system_prefix = self.real_prefix or self.base_prefix or self.prefix
        confs = {
            k: (system_prefix if isinstance(v, str) and v.startswith(self.prefix) else v)
            for k, v in self.sysconfig_vars.items()
        }
        self.system_stdlib = self._sysconfig_path("stdlib", confs)
        self.system_stdlib_platform = self._sysconfig_path("platstdlib", confs)
        self.max_size = getattr(sys, "maxsize", getattr(sys, "maxint", None))
        self._creators = None  # virtualenv-specific, set via monkey-patch

    @staticmethod
    def _get_tcl_tk_libs():  # pragma: no cover # tkinter availability varies; tested indirectly via __init__
        # Detect the tcl and tk libraries using tkinter.
        tcl_lib, tk_lib = None, None
        try:
            import tkinter as tk  # ruff:ignore[import-outside-top-level] # novermin # unreached below the version gate
        except ImportError:
            pass
        else:
            # Tk.__init__ reads profile scripts from HOME or the working directory; probing needs only library metadata.
            class _TclWithoutProfile(tk.Tk):
                def readprofile(self, *_args, **_kwargs):  # ruff:ignore[no-self-use] Tk override
                    return None

            try:
                tcl = _TclWithoutProfile(useTk=False)
                tcl_lib = tcl.eval("info library")
                tk_lib = PythonInfoCollector._resolve_tk_lib(tcl, tcl_lib)
            except tk.TclError:
                pass

        return tcl_lib, tk_lib

    @staticmethod
    def _resolve_tk_lib(tcl, tcl_lib):  # pragma: no cover # Tk is absent on test runners
        # Resolve the TK library path by direct query or path construction.
        tk_lib = PythonInfoCollector._query_tk_library(tcl)
        if tk_lib is not None:
            return tk_lib
        import _tkinter  # ruff:ignore[import-outside-top-level,import-private-name] # simplint: ignore[private-import-path] # novermin

        tcl_parent = os.path.dirname(tcl_lib)
        version_text = _tkinter.TK_VERSION
        for version in (version_text, version_text.split(".", maxsplit=1)[0]):
            tk_lib_path = os.path.join(tcl_parent, "tk{}".format(version))
            if os.path.isdir(tk_lib_path) and os.path.exists(os.path.join(tk_lib_path, "tk.tcl")):
                return tk_lib_path
        return None

    @staticmethod
    def _query_tk_library(tcl):  # pragma: no cover, Tcl probing needs a Tk install the test runners lack
        # Try to get the TK library path directly from Tcl.
        import tkinter as tk  # ruff:ignore[import-outside-top-level] # novermin # unreached below the version gate

        try:
            tk_lib = tcl.eval("set tk_library")
            if tk_lib and os.path.isdir(tk_lib):
                return tk_lib
        except tk.TclError:
            pass
        return None

    def _sysconfig_path(self, key, config_var):
        pattern = self.sysconfig_paths.get(key)
        if pattern is None:  # custom builds may ship schemes without stdlib / platstdlib
            return ""
        base = self.sysconfig_vars.copy()
        base.update(config_var)
        return pattern.format(**base).replace("/", os.sep)

    def to_dict(self):
        # Convert the collected information to a plain dictionary.
        data = {var: (getattr(self, var) if var != "_creators" else None) for var in self.__dict__}
        data["version_info"] = self.version_info._asdict()
        return data


def _main():  # pragma: no cover # exercised via subprocess runs
    argv = sys.argv[1:]

    if len(argv) >= 1:
        start_cookie = argv[0]
        argv = argv[1:]
    else:
        start_cookie = ""

    if len(argv) >= 1:
        end_cookie = argv[0]
        argv = argv[1:]
    else:
        end_cookie = ""

    sys.argv = sys.argv[:1] + argv

    result = json.dumps(PythonInfoCollector().to_dict(), indent=2)
    sys.stdout.write("".join((start_cookie[::-1], result, end_cookie[::-1])))
    sys.stdout.flush()


__all__ = [
    "MIN_INTERROGATE_VERSION",
    "UNSUPPORTED_EXIT_CODE",
    "UNSUPPORTED_MARKER",
    "PythonInfoCollector",
]

if __name__ == "__main__":
    _main()
