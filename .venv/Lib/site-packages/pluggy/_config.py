"""
Configuration types for hook specifications and implementations.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TypedDict


class HookspecOpts(TypedDict):
    """Options for a hook specification."""

    #: Whether the hook is :ref:`first result only <firstresult>`.
    firstresult: bool
    #: Whether the hook is :ref:`historic <historic>`.
    historic: bool
    #: Whether the hook :ref:`warns when implemented <warn_on_impl>`.
    warn_on_impl: Warning | None
    #: Whether the hook warns when :ref:`certain arguments are requested
    #: <warn_on_impl>`.
    #:
    #: .. versionadded:: 1.5
    warn_on_impl_args: Mapping[str, Warning] | None


class HookimplOpts(TypedDict):
    """Options for a hook implementation."""

    #: Whether the hook implementation is a :ref:`wrapper <hookwrapper>`.
    wrapper: bool
    #: Whether the hook implementation is an :ref:`old-style wrapper
    #: <old_style_hookwrappers>`.
    hookwrapper: bool
    #: Whether validation against a hook specification is :ref:`optional
    #: <optionalhook>`.
    optionalhook: bool
    #: Whether to try to order this hook implementation :ref:`first
    #: <callorder>`.
    tryfirst: bool
    #: Whether to try to order this hook implementation :ref:`last
    #: <callorder>`.
    trylast: bool
    #: The name of the hook specification to match, see :ref:`specname`.
    specname: str | None


def normalize_hookimpl_opts(opts: HookimplOpts) -> None:
    opts.setdefault("tryfirst", False)
    opts.setdefault("trylast", False)
    opts.setdefault("wrapper", False)
    opts.setdefault("hookwrapper", False)
    opts.setdefault("optionalhook", False)
    opts.setdefault("specname", None)
