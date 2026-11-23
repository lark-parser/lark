"""
Hook callers and relay.
"""

from __future__ import annotations

from collections.abc import Callable
from collections.abc import Mapping
from collections.abc import Sequence
from collections.abc import Set as AbstractSet
from typing import Any
from typing import Final
from typing import final
from typing import TYPE_CHECKING
from typing import TypeAlias
import warnings

from ._config import HookimplOpts
from ._config import HookspecOpts
from ._decorators import _Namespace
from ._decorators import HookSpec
from ._impl import _Plugin
from ._impl import HookImpl


_HookExec: TypeAlias = Callable[
    [str, Sequence[HookImpl], Mapping[str, object], bool],
    object | list[object],
]


@final
class HookRelay:
    """Hook holder object for performing 1:N hook calls where N is the number
    of registered plugins."""

    __slots__ = ("__dict__",)

    def __init__(self) -> None:
        """:meta private:"""

    if TYPE_CHECKING:

        def __getattr__(self, name: str) -> HookCaller: ...


# Historical name (pluggy<=1.2), kept for backward compatibility.
_HookRelay = HookRelay


_CallHistory: TypeAlias = list[
    tuple[Mapping[str, object], Callable[[Any], None] | None]
]


class HookCaller:
    """A caller of all registered implementations of a hook specification."""

    __slots__ = (
        "_call_history",
        "_hookexec",
        "_hookimpls",
        "name",
        "spec",
    )

    def __init__(
        self,
        name: str,
        hook_execute: _HookExec,
        specmodule_or_class: _Namespace | None = None,
        spec_opts: HookspecOpts | None = None,
    ) -> None:
        """:meta private:"""
        #: Name of the hook getting called.
        self.name: Final = name
        self._hookexec: Final = hook_execute
        # The hookimpls list. The caller iterates it *in reverse*. Format:
        # 1. trylast nonwrappers
        # 2. nonwrappers
        # 3. tryfirst nonwrappers
        # 4. trylast wrappers
        # 5. wrappers
        # 6. tryfirst wrappers
        self._hookimpls: Final[list[HookImpl]] = []
        self._call_history: _CallHistory | None = None
        # TODO: Document, or make private.
        self.spec: HookSpec | None = None
        if specmodule_or_class is not None:
            assert spec_opts is not None
            self.set_specification(specmodule_or_class, spec_opts)

    # TODO: Document, or make private.
    def has_spec(self) -> bool:
        return self.spec is not None

    # TODO: Document, or make private.
    def set_specification(
        self,
        specmodule_or_class: _Namespace,
        spec_opts: HookspecOpts,
    ) -> None:
        if self.spec is not None:
            raise ValueError(
                f"Hook {self.spec.name!r} is already registered "
                f"within namespace {self.spec.namespace}"
            )
        self.spec = HookSpec(specmodule_or_class, self.name, spec_opts)
        if spec_opts.get("historic"):
            self._call_history = []

    def is_historic(self) -> bool:
        """Whether this caller is :ref:`historic <historic>`."""
        return self._call_history is not None

    def _remove_plugin(self, plugin: _Plugin) -> None:
        """Remove all hook implementations registered by the given plugin."""
        remaining = [impl for impl in self._hookimpls if impl.plugin != plugin]
        if len(remaining) == len(self._hookimpls):
            raise ValueError(f"plugin {plugin!r} not found")
        self._hookimpls[:] = remaining

    def get_hookimpls(self) -> list[HookImpl]:
        """Get all registered hook implementations for this hook."""
        return self._hookimpls.copy()

    def _add_hookimpl(self, hookimpl: HookImpl) -> None:
        """Add an implementation to the callback chain."""
        for i, method in enumerate(self._hookimpls):
            if method.hookwrapper or method.wrapper:
                splitpoint = i
                break
        else:
            splitpoint = len(self._hookimpls)
        if hookimpl.hookwrapper or hookimpl.wrapper:
            start, end = splitpoint, len(self._hookimpls)
        else:
            start, end = 0, splitpoint

        if hookimpl.trylast:
            self._hookimpls.insert(start, hookimpl)
        elif hookimpl.tryfirst:
            self._hookimpls.insert(end, hookimpl)
        else:
            # find last non-tryfirst method
            i = end - 1
            while i >= start and self._hookimpls[i].tryfirst:
                i -= 1
            self._hookimpls.insert(i + 1, hookimpl)

    def __repr__(self) -> str:
        return f"<HookCaller {self.name!r}>"

    def _apply_defaults(self, kwargs: Mapping[str, object]) -> Mapping[str, object]:
        if self.spec is None or not self.spec.kwargdefaults:
            return kwargs
        return {**self.spec.kwargdefaults, **kwargs}

    def _verify_all_args_are_provided(self, kwargs: Mapping[str, object]) -> None:
        # This is written to avoid expensive operations when not needed.
        if self.spec:
            for argname in self.spec.argnames:
                if argname not in kwargs:
                    notincall = ", ".join(
                        repr(argname)
                        for argname in self.spec.argnames
                        # Avoid self.spec.argnames - kwargs.keys()
                        # it doesn't preserve order.
                        if argname not in kwargs
                    )
                    warnings.warn(
                        f"Argument(s) {notincall} which are declared in the hookspec "
                        "cannot be found in this hook call",
                        # 3, not 2: the warning is raised in this helper, which
                        # is called by __call__/call_historic/call_extra, which
                        # are called by the code making the hook call.
                        stacklevel=3,
                    )
                    break

    def __call__(self, **kwargs: object) -> Any:
        """Call the hook.

        Only accepts keyword arguments, which should match the hook
        specification.

        Returns the result(s) of calling all registered plugins, see
        :ref:`calling`.
        """
        assert not self.is_historic(), (
            "Cannot directly call a historic hook - use call_historic instead."
        )
        call_kwargs = self._apply_defaults(kwargs)
        self._verify_all_args_are_provided(call_kwargs)
        firstresult = self.spec.opts.get("firstresult", False) if self.spec else False
        # Copy because plugins may register other plugins during iteration (#438).
        return self._hookexec(
            self.name, self._hookimpls.copy(), call_kwargs, firstresult
        )

    def call_historic(
        self,
        result_callback: Callable[[Any], None] | None = None,
        kwargs: Mapping[str, object] | None = None,
    ) -> None:
        """Call the hook with given ``kwargs`` for all registered plugins and
        for all plugins which will be registered afterwards, see
        :ref:`historic`.

        :param result_callback:
            If provided, will be called for each non-``None`` result obtained
            from a hook implementation.
        """
        assert self._call_history is not None
        kwargs = kwargs or {}
        kwargs = self._apply_defaults(kwargs)
        self._verify_all_args_are_provided(kwargs)
        self._call_history.append((kwargs, result_callback))
        # Historizing hooks don't return results.
        # Remember firstresult isn't compatible with historic.
        # Copy because plugins may register other plugins during iteration (#438).
        res = self._hookexec(self.name, self._hookimpls.copy(), kwargs, False)
        if result_callback is None:
            return
        if isinstance(res, list):
            for x in res:
                result_callback(x)

    def call_extra(
        self, methods: Sequence[Callable[..., object]], kwargs: Mapping[str, object]
    ) -> Any:
        """Call the hook with some additional temporarily participating
        methods using the specified ``kwargs`` as call parameters, see
        :ref:`call_extra`."""
        assert not self.is_historic(), (
            "Cannot directly call a historic hook - use call_historic instead."
        )
        kwargs = self._apply_defaults(kwargs)
        self._verify_all_args_are_provided(kwargs)
        opts: HookimplOpts = {
            "wrapper": False,
            "hookwrapper": False,
            "optionalhook": False,
            "trylast": False,
            "tryfirst": False,
            "specname": None,
        }
        hookimpls = self._hookimpls.copy()
        for method in methods:
            hookimpl = HookImpl(None, "<temp>", method, opts)
            # Find last non-tryfirst nonwrapper method.
            i = len(hookimpls) - 1
            while i >= 0 and (
                # Skip wrappers.
                (hookimpls[i].hookwrapper or hookimpls[i].wrapper)
                # Skip tryfirst nonwrappers.
                or hookimpls[i].tryfirst
            ):
                i -= 1
            hookimpls.insert(i + 1, hookimpl)
        firstresult = self.spec.opts.get("firstresult", False) if self.spec else False
        return self._hookexec(self.name, hookimpls, kwargs, firstresult)

    def _maybe_apply_history(self, method: HookImpl) -> None:
        """Apply call history to a new hookimpl if it is marked as historic."""
        if self.is_historic():
            assert self._call_history is not None
            for kwargs, result_callback in self._call_history:
                res = self._hookexec(self.name, [method], kwargs, False)
                if res and result_callback is not None:
                    # XXX: remember firstresult isn't compat with historic
                    assert isinstance(res, list)
                    result_callback(res[0])


# Historical name (pluggy<=1.2), kept for backward compatibility.
_HookCaller = HookCaller


class _SubsetHookCaller(HookCaller):
    """A proxy to another HookCaller which manages calls to all registered
    plugins except the ones from remove_plugins."""

    # This class is unusual: in inhertits from `HookCaller` so all of
    # the *code* runs in the class, but it delegates all underlying *data*
    # to the original HookCaller.
    # `subset_hook_caller` used to be implemented by creating a full-fledged
    # HookCaller, copying all hookimpls from the original. This had problems
    # with memory leaks (#346) and historic calls (#347), which make a proxy
    # approach better.
    # An alternative implementation is to use a `_getattr__`/`__getattribute__`
    # proxy, however that adds more overhead and is more tricky to implement.

    __slots__ = (
        "_orig",
        "_remove_plugins",
    )

    def __init__(self, orig: HookCaller, remove_plugins: AbstractSet[_Plugin]) -> None:
        self._orig = orig
        self._remove_plugins = remove_plugins
        self.name = orig.name  # type: ignore[misc]
        self._hookexec = orig._hookexec  # type: ignore[misc]

    @property  # type: ignore[misc]
    def _hookimpls(self) -> list[HookImpl]:
        return [
            impl
            for impl in self._orig._hookimpls
            if impl.plugin not in self._remove_plugins
        ]

    @property
    def spec(self) -> HookSpec | None:  # type: ignore[override]
        return self._orig.spec

    @property
    def _call_history(self) -> _CallHistory | None:  # type: ignore[override]
        return self._orig._call_history

    def __repr__(self) -> str:
        return f"<_SubsetHookCaller {self.name!r}>"
