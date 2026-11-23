# This file must be used with "source bin/activate.xsh" *from xonsh*.
# You cannot run it directly.


class _VirtualEnvActivator:
    """xonsh activation for virtualenv.

    Rendered into ``<venv>/bin/activate.xsh`` by the template in
    ``src/virtualenv/activation/xonsh/`` at generate-time.

    - Project: https://github.com/pypa/virtualenv
    - Template source: https://github.com/pypa/virtualenv/tree/main/src/virtualenv/activation/xonsh
    """

    def __init__(self):
        self.env = __xonsh__.env
        self.unset_vars = set()
        try:
            # Values substituted by virtualenv's XonshActivator at generate-time.
            # If this file was sourced before template rendering, the bare
            # identifiers below resolve to NameError.
            self.embedded_virtual_env = self._fs_path(__VIRTUAL_ENV__, required=True)
            self.embedded_virtual_prompt = __VIRTUAL_PROMPT__
            self.embedded_bin_name = __BIN_NAME__
            self.embedded_tcl_library = self._fs_path(__TCL_LIBRARY__)
            self.embedded_tk_library = self._fs_path(__TK_LIBRARY__)
        except NameError:
            print("virtualenv activate.xsh: template was not rendered")
            raise
        # Variables this activator may save+override; deactivate walks this list.
        self.managed_vars = ("PATH", "PKG_CONFIG_PATH", "PYTHONHOME", "TCL_LIBRARY", "TK_LIBRARY")
        self.pydoc_registered = False
        self.saved_pydoc = None

    @staticmethod
    def _fs_path(value, required=False):
        import builtins
        import os

        if not builtins.isinstance(value, builtins.bytes):
            return value
        decoded = os.fsdecode(value)
        if os.fsencode(decoded) == value:
            return decoded
        if required:
            raise builtins.ValueError(f"virtualenv activate.xsh: the filesystem codec cannot represent {value!r}")
        return ""

    def _backup_name(self, name):
        return f"_OLD_VIRTUAL_{name}"

    def _save(self, name):
        backup = self._backup_name(name)
        if name in self.env:
            self.env[backup] = self.env[name]
        else:
            self.unset_vars.add(name)
            self.env.pop(backup, None)

    def _override(self, name, value):
        self._save(name)
        self.env[name] = value

    def _drop(self, name):
        self._save(name)
        self.env.pop(name, None)

    def register_pydoc(self):
        self.saved_pydoc = aliases["pydoc"] if "pydoc" in aliases else None
        aliases["pydoc"] = ["python", "-m", "pydoc"]
        self.pydoc_registered = True

    def unregister_pydoc(self):
        if not self.pydoc_registered:
            return
        if self.saved_pydoc is None:
            aliases.pop("pydoc", None)
        else:
            aliases["pydoc"] = self.saved_pydoc
        self.pydoc_registered = False
        self.saved_pydoc = None

    def activate(self):
        from os.path import join, basename

        if hasattr(__xonsh__.xontrib, "virtualenv"):
            __xonsh__.xontrib.virtualenv.deactivate(["nondestructive"])
        __xonsh__.xontrib.virtualenv = self
        aliases["deactivate"] = self.deactivate
        self.deactivate(["nondestructive"])  # wipe any stale state from a prior activation

        $VIRTUAL_ENV = self.embedded_virtual_env
        $VIRTUAL_ENV_PROMPT = self.embedded_virtual_prompt or basename($VIRTUAL_ENV)

        self._override("PATH", [join($VIRTUAL_ENV, self.embedded_bin_name), *$PATH])
        self._override(
            "PKG_CONFIG_PATH", [join($VIRTUAL_ENV, "lib", "pkgconfig"), *self.env.get("PKG_CONFIG_PATH", [])]
        )
        self._drop("PYTHONHOME")
        for name, value in (("TCL_LIBRARY", self.embedded_tcl_library), ("TK_LIBRARY", self.embedded_tk_library)):
            if value:
                self._override(name, value)

        self.register_pydoc()

    def deactivate(self, args=None):
        for name in self.managed_vars:
            backup = self._backup_name(name)
            if backup in self.env:
                self.env[name] = self.env.pop(backup)
            elif name in self.unset_vars:
                self.env.pop(name, None)
        self.unset_vars.clear()
        for name in ("VIRTUAL_ENV", "VIRTUAL_ENV_PROMPT"):
            self.env.pop(name, None)
        self.unregister_pydoc()
        if args is None or "nondestructive" not in args:
            del aliases["deactivate"]
            try:
                del __xonsh__.xontrib.virtualenv
            except AttributeError:
                pass


if not hasattr(__xonsh__, "xontrib"):
    __xonsh__.xontrib = __xonsh__.imp.types.SimpleNamespace()
_VirtualEnvActivator().activate()
