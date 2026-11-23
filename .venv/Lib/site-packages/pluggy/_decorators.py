"""
Hook markers, specifications, and related helpers.
"""

from __future__ import annotations

from collections.abc import Callable
from collections.abc import Mapping
import inspect
import sys
import types
from types import ModuleType
from typing import Final
from typing import final
from typing import overload
from typing import TypeAlias
from typing import TypeVar
import warnings

from ._config import HookimplOpts
from ._config import HookspecOpts


_F = TypeVar("_F", bound=Callable[..., object])

_Namespace: TypeAlias = ModuleType | type


@final
class HookspecMarker:
    """Decorator for marking functions as hook specifications.

    Instantiate it with a project_name to get a decorator.
    Calling :meth:`PluginManager.add_hookspecs` later will discover all marked
    functions if the :class:`PluginManager` uses the same project name.
    """

    __slots__ = ("project_name",)

    def __init__(self, project_name: str) -> None:
        self.project_name: Final = project_name

    @overload
    def __call__(
        self,
        function: _F,
        firstresult: bool = False,
        historic: bool = False,
        warn_on_impl: Warning | None = None,
        warn_on_impl_args: Mapping[str, Warning] | None = None,
    ) -> _F: ...

    @overload
    def __call__(
        self,
        function: None = ...,
        firstresult: bool = ...,
        historic: bool = ...,
        warn_on_impl: Warning | None = ...,
        warn_on_impl_args: Mapping[str, Warning] | None = ...,
    ) -> Callable[[_F], _F]: ...

    def __call__(
        self,
        function: _F | None = None,
        firstresult: bool = False,
        historic: bool = False,
        warn_on_impl: Warning | None = None,
        warn_on_impl_args: Mapping[str, Warning] | None = None,
    ) -> _F | Callable[[_F], _F]:
        """If passed a function, directly sets attributes on the function
        which will make it discoverable to :meth:`PluginManager.add_hookspecs`.

        If passed no function, returns a decorator which can be applied to a
        function later using the attributes supplied.

        :param firstresult:
            If ``True``, the 1:N hook call (N being the number of registered
            hook implementation functions) will stop at I<=N when the I'th
            function returns a non-``None`` result. See :ref:`firstresult`.

        :param historic:
            If ``True``, every call to the hook will be memorized and replayed
            on plugins registered after the call was made. See :ref:`historic`.

        :param warn_on_impl:
            If given, every implementation of this hook will trigger the given
            warning. See :ref:`warn_on_impl`.

        :param warn_on_impl_args:
            If given, every implementation of this hook which requests one of
            the arguments in the dict will trigger the corresponding warning.
            See :ref:`warn_on_impl`.

            .. versionadded:: 1.5
        """

        def setattr_hookspec_opts(func: _F) -> _F:
            if historic and firstresult:
                raise ValueError("cannot have a historic firstresult hook")
            opts: HookspecOpts = {
                "firstresult": firstresult,
                "historic": historic,
                "warn_on_impl": warn_on_impl,
                "warn_on_impl_args": warn_on_impl_args,
            }
            setattr(func, self.project_name + "_spec", opts)
            return func

        if function is not None:
            return setattr_hookspec_opts(function)
        else:
            return setattr_hookspec_opts


@final
class HookimplMarker:
    """Decorator for marking functions as hook implementations.

    Instantiate it with a ``project_name`` to get a decorator.
    Calling :meth:`PluginManager.register` later will discover all marked
    functions if the :class:`PluginManager` uses the same project name.
    """

    __slots__ = ("project_name",)

    def __init__(self, project_name: str) -> None:
        self.project_name: Final = project_name

    @overload
    def __call__(
        self,
        function: _F,
        hookwrapper: bool = ...,
        optionalhook: bool = ...,
        tryfirst: bool = ...,
        trylast: bool = ...,
        specname: str | None = ...,
        wrapper: bool = ...,
    ) -> _F: ...

    @overload
    def __call__(
        self,
        function: None = ...,
        hookwrapper: bool = ...,
        optionalhook: bool = ...,
        tryfirst: bool = ...,
        trylast: bool = ...,
        specname: str | None = ...,
        wrapper: bool = ...,
    ) -> Callable[[_F], _F]: ...

    def __call__(
        self,
        function: _F | None = None,
        hookwrapper: bool = False,
        optionalhook: bool = False,
        tryfirst: bool = False,
        trylast: bool = False,
        specname: str | None = None,
        wrapper: bool = False,
    ) -> _F | Callable[[_F], _F]:
        """If passed a function, directly sets attributes on the function
        which will make it discoverable to :meth:`PluginManager.register`.

        If passed no function, returns a decorator which can be applied to a
        function later using the attributes supplied.

        :param optionalhook:
            If ``True``, a missing matching hook specification will not result
            in an error (by default it is an error if no matching spec is
            found). See :ref:`optionalhook`.

        :param tryfirst:
            If ``True``, this hook implementation will run as early as possible
            in the chain of N hook implementations for a specification. See
            :ref:`callorder`.

        :param trylast:
            If ``True``, this hook implementation will run as late as possible
            in the chain of N hook implementations for a specification. See
            :ref:`callorder`.

        :param wrapper:
            If ``True`` ("new-style hook wrapper"), the hook implementation
            needs to execute exactly one ``yield``. The code before the
            ``yield`` is run early before any non-hook-wrapper function is run.
            The code after the ``yield`` is run after all non-hook-wrapper
            functions have run. The ``yield`` receives the result value of the
            inner calls, or raises the exception of inner calls (including
            earlier hook wrapper calls). The return value of the function
            becomes the return value of the hook, and a raised exception becomes
            the exception of the hook. See :ref:`hookwrapper`.

        :param hookwrapper:
            If ``True`` ("old-style hook wrapper"), the hook implementation
            needs to execute exactly one ``yield``. The code before the
            ``yield`` is run early before any non-hook-wrapper function is run.
            The code after the ``yield`` is run after all non-hook-wrapper
            function have run  The ``yield`` receives a :class:`Result` object
            representing the exception or result outcome of the inner calls
            (including earlier hook wrapper calls). This option is mutually
            exclusive with ``wrapper``. See :ref:`old_style_hookwrapper`.

        :param specname:
            If provided, the given name will be used instead of the function
            name when matching this hook implementation to a hook specification
            during registration. See :ref:`specname`.

        .. versionadded:: 1.2.0
            The ``wrapper`` parameter.
        """

        def setattr_hookimpl_opts(func: _F) -> _F:
            opts: HookimplOpts = {
                "wrapper": wrapper,
                "hookwrapper": hookwrapper,
                "optionalhook": optionalhook,
                "tryfirst": tryfirst,
                "trylast": trylast,
                "specname": specname,
            }
            setattr(func, self.project_name + "_impl", opts)
            return func

        if function is None:
            return setattr_hookimpl_opts
        else:
            return setattr_hookimpl_opts(function)


_PYPY = sys.implementation.name == "pypy"
_IMPLICIT_NAMES = ("self", "cls", "obj") if _PYPY else ("self", "cls")

# Qualnames whose missing-self deprecation warning is suppressed because
# their upstream code is already fixed but not yet released.
# Remove entries once a release with the fix is available.
_NOSELF_WARN_SUPPRESS: frozenset[str] = frozenset(
    {
        # pytest-timeout >=2.3.2 has the fix, but is unreleased as of 2026-05.
        "TimeoutHooks.pytest_timeout_set_timer",
        "TimeoutHooks.pytest_timeout_cancel_timer",
    }
)


def varnames(
    func: object, *, legacy_noself: bool = False
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return tuple of positional and keyword parameter names for a callable.

    In case of a class, its ``__init__`` method is considered.
    For bound methods, the already-bound first parameter is not included.
    For unbound methods with a dotted ``__qualname__``, the first parameter is
    stripped only if its name is a known implicit name (``self``, ``cls``).
    Keyword-only parameters are not included.

    :param legacy_noself:
        If ``True``, support hookspec classes whose methods omit ``self``.
        When the function looks like a class method but has no implicit first
        parameter, a :class:`DeprecationWarning` is emitted.
    """
    is_bound = False
    if inspect.isclass(func):
        try:
            func = func.__init__
        except AttributeError:  # pragma: no cover - pypy special case
            return (), ()
        is_bound = True
    elif not inspect.isroutine(func):  # callable object?
        try:
            # Not a `callable()` check: the `__call__` attribute itself is
            # wanted, so that its signature can be inspected below.
            func = getattr(func, "__call__", func)  # noqa: B004
        except Exception:  # pragma: no cover - pypy special case
            return (), ()

    # Track bound methods before unwrapping, since __func__ loses that info.
    if inspect.ismethod(func):
        is_bound = True
    func = inspect.unwrap(func)  # type: ignore[arg-type]
    if inspect.ismethod(func):
        is_bound = True
        func = func.__func__

    try:
        code: types.CodeType = func.__code__  # type: ignore[attr-defined]
        defaults: tuple[object, ...] | None = func.__defaults__  # type: ignore[attr-defined]
        qualname: str = func.__qualname__  # type: ignore[attr-defined]
    except AttributeError:  # pragma: no cover
        return (), ()

    # Get positional argument names (positional-only + positional-or-keyword)
    args: tuple[str, ...] = code.co_varnames[: code.co_argcount]

    # Determine which args have defaults
    kwargs: tuple[str, ...]
    if defaults:
        index = -len(defaults)
        args, kwargs = args[:index], args[index:]
    else:
        kwargs = ()

    # Strip implicit instance/class arg.
    # Check if this looks like a method defined in a class by examining the
    # qualname after the last "<locals>." segment (if any). A remaining dot
    # means it's a class method (e.g. "MyClass.method" or
    # "func.<locals>.MyClass.method"), not just a nested function.
    _tail = qualname.rsplit("<locals>.", maxsplit=1)[-1]
    _is_class_method = "." in _tail
    if args:
        if is_bound or (_is_class_method and args[0] in _IMPLICIT_NAMES):
            args = args[1:]
        elif _is_class_method and legacy_noself and _tail not in _NOSELF_WARN_SUPPRESS:
            warnings.warn(
                f"{qualname} is a method but its first parameter"
                f" {args[0]!r} is not 'self'."
                f" Add 'self' as the first parameter or use @staticmethod."
                f" This will become an error in a future version of pluggy.",
                DeprecationWarning,
                stacklevel=2,
            )

    return args, kwargs


@final
class HookSpec:
    __slots__ = (
        "argnames",
        "function",
        "kwargdefaults",
        "kwargnames",
        "name",
        "namespace",
        "opts",
        "warn_on_impl",
        "warn_on_impl_args",
    )

    def __init__(self, namespace: _Namespace, name: str, opts: HookspecOpts) -> None:
        self.namespace = namespace
        self.name = name
        self.function: Callable[..., object] = getattr(namespace, name)
        legacy_noself = inspect.isclass(namespace) and not isinstance(
            inspect.getattr_static(namespace, name), staticmethod
        )
        self.argnames, self.kwargnames = varnames(
            self.function, legacy_noself=legacy_noself
        )
        defaults = inspect.unwrap(self.function).__defaults__
        self.kwargdefaults = dict(zip(self.kwargnames, defaults or ()))
        self.opts = opts
        self.warn_on_impl = opts.get("warn_on_impl")
        self.warn_on_impl_args = opts.get("warn_on_impl_args")
