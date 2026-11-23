from __future__ import annotations

__lazy_modules__ = [f"{__spec__.parent}"]  # ty: ignore[missing-union-attribute]  # imported modules have a spec

from . import add_version_flag, build_parser, build_parser_only, handle_extra_commands, load_app_data

__all__ = [
    "add_version_flag",
    "build_parser",
    "build_parser_only",
    "handle_extra_commands",
    "load_app_data",
]
