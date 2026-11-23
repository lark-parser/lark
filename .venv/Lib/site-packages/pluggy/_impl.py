"""
Hook implementation representation.
"""

from __future__ import annotations

from collections.abc import Callable
from collections.abc import Generator
from typing import Final
from typing import final
from typing import TypeAlias
from typing import TypeVar

from ._config import HookimplOpts
from ._decorators import varnames
from ._result import Result


_T = TypeVar("_T")

_Plugin: TypeAlias = object
_HookImplFunction: TypeAlias = Callable[..., _T | Generator[None, Result[_T], None]]


@final
class HookImpl:
    """A hook implementation in a :class:`HookCaller`."""

    __slots__ = (
        "argnames",
        "function",
        "hookwrapper",
        "kwargnames",
        "optionalhook",
        "opts",
        "plugin",
        "plugin_name",
        "tryfirst",
        "trylast",
        "wrapper",
    )

    def __init__(
        self,
        plugin: _Plugin,
        plugin_name: str,
        function: _HookImplFunction[object],
        hook_impl_opts: HookimplOpts,
    ) -> None:
        """:meta private:"""
        #: The hook implementation function.
        self.function: Final = function
        argnames, kwargnames = varnames(self.function)
        #: The positional parameter names of ``function``.
        self.argnames: Final = argnames
        #: The keyword parameter names of ``function`` which declare defaults.
        #: Keyword-only parameters are *not* included.
        self.kwargnames: Final = kwargnames
        #: The plugin which defined this hook implementation.
        self.plugin: Final = plugin
        #: The :class:`HookimplOpts` used to configure this hook implementation.
        self.opts: Final = hook_impl_opts
        #: The name of the plugin which defined this hook implementation.
        self.plugin_name: Final = plugin_name
        #: Whether the hook implementation is a :ref:`wrapper <hookwrapper>`.
        self.wrapper: Final = hook_impl_opts["wrapper"]
        #: Whether the hook implementation is an :ref:`old-style wrapper
        #: <old_style_hookwrappers>`.
        self.hookwrapper: Final = hook_impl_opts["hookwrapper"]
        #: Whether validation against a hook specification is :ref:`optional
        #: <optionalhook>`.
        self.optionalhook: Final = hook_impl_opts["optionalhook"]
        #: Whether to try to order this hook implementation :ref:`first
        #: <callorder>`.
        self.tryfirst: Final = hook_impl_opts["tryfirst"]
        #: Whether to try to order this hook implementation :ref:`last
        #: <callorder>`.
        self.trylast: Final = hook_impl_opts["trylast"]

    def __repr__(self) -> str:
        return f"<HookImpl plugin_name={self.plugin_name!r}, plugin={self.plugin!r}>"
