"""Persistence and caching utilities for Lark.

Contains functions for saving, loading, and caching Lark parser instances.
"""

import getpass
import sys
import os
import pickle
import tempfile
from typing import Dict, Any, Union, Collection, Optional, Type, TypeVar

from .utils import SerializeMemoizer, FS, logger
from .serialize import Serialize
from .exceptions import ConfigurationError
from .options import LarkOptions, _LOAD_ALLOWED_OPTIONS

if False:
    from .lexer import TerminalDef, LexerConf
    from .grammar import Rule
    from .grammar_builder import Grammar
    from .parser_frontends import _deserialize_parsing_frontend, _validate_frontend_args, _get_lexer_callbacks

_T = TypeVar('_T')


def lark_save(lark_instance, f, exclude_options: Collection[str] = ()) -> None:
    """Saves the Lark instance into the given file object

    Useful for caching and multiprocessing.
    """
    from .grammar import Rule
    from .lexer import TerminalDef

    if lark_instance.options.parser != 'lalr':
        raise NotImplementedError("Lark.save() is only implemented for the LALR(1) parser.")
    data, m = lark_instance.memo_serialize([TerminalDef, Rule])
    if exclude_options:
        data["options"] = {n: v for n, v in data["options"].items() if n not in exclude_options}
    pickle.dump({'data': data, 'memo': m}, f, protocol=pickle.HIGHEST_PROTOCOL)


def lark_load(cls: Type[_T], f) -> _T:
    """Loads a Lark instance from the given file object

    Useful for caching and multiprocessing.
    """
    inst = cls.__new__(cls)
    return lark_load_into(inst, f)


def lark_deserialize_lexer_conf(data: Dict[str, Any], memo: Dict[int, Any], options: LarkOptions) -> Any:
    """Deserialize lexer configuration from saved data."""
    import re
    from .common import LexerConf

    try:
        import regex
    except ImportError:
        regex = None

    lexer_conf = LexerConf.deserialize(data['lexer_conf'], memo)
    lexer_conf.callbacks = options.lexer_callbacks or {}
    lexer_conf.re_module = regex if options.regex else re
    lexer_conf.use_bytes = options.use_bytes
    lexer_conf.g_regex_flags = options.g_regex_flags
    lexer_conf.skip_validation = True
    lexer_conf.postlex = options.postlex
    return lexer_conf


def lark_load_into(lark_instance, f: Any, **kwargs):
    """Load saved data into an existing Lark instance."""
    from .grammar import Rule
    from .grammar_builder import Grammar
    from .lexer import TerminalDef
    from .parser_frontends import _deserialize_parsing_frontend, _validate_frontend_args

    if isinstance(f, dict):
        d = f
    else:
        d = pickle.load(f)
    memo_json = d['memo']
    data = d['data']

    assert memo_json
    memo = SerializeMemoizer.deserialize(memo_json, {'Rule': Rule, 'TerminalDef': TerminalDef}, {})
    if 'grammar' in data:
        lark_instance.grammar = Grammar.deserialize(data['grammar'], memo)
    options = dict(data['options'])
    if (set(kwargs) - _LOAD_ALLOWED_OPTIONS) & set(LarkOptions._defaults):
        raise ConfigurationError("Some options are not allowed when loading a Parser: {}"
                         .format(set(kwargs) - _LOAD_ALLOWED_OPTIONS))
    options.update(kwargs)
    lark_instance.options = LarkOptions.deserialize(options, memo)
    lark_instance.rules = [Rule.deserialize(r, memo) for r in data['rules']]
    lark_instance.source_path = '<deserialized>'
    _validate_frontend_args(lark_instance.options.parser, lark_instance.options.lexer)
    lark_instance.lexer_conf = lark_deserialize_lexer_conf(data['parser'], memo, lark_instance.options)
    lark_instance.terminals = lark_instance.lexer_conf.terminals
    lark_instance._prepare_callbacks()
    lark_instance._terminals_dict = {t.name: t for t in lark_instance.terminals}
    lark_instance.parser = _deserialize_parsing_frontend(
        data['parser'],
        memo,
        lark_instance.lexer_conf,
        lark_instance._callbacks,
        lark_instance.options,  # Not all, but multiple attributes are used
    )
    return lark_instance


def lark_load_from_dict(cls, data, memo, **kwargs):
    """Load a Lark instance from a dictionary."""
    inst = cls.__new__(cls)
    return lark_load_into(inst, {'data': data, 'memo': memo}, **kwargs)


def resolve_cache_fn(options: LarkOptions, grammar: str, options_dict: Dict[str, Any]) -> Optional[str]:
    """Resolve the cache filename based on options and grammar.

    Returns the cache filename, or None if caching is not enabled.
    """
    from .load_grammar import sha256_digest

    if not options.cache:
        return None

    if options.parser != 'lalr':
        raise ConfigurationError("cache only works with parser='lalr' for now")

    unhashable = ('transformer', 'postlex', 'lexer_callbacks', 'edit_terminals', '_plugins')
    options_str = ''.join(k+str(v) for k, v in options_dict.items() if k not in unhashable)
    from . import __version__
    s = grammar + options_str + __version__ + str(sys.version_info[:2])
    cache_sha256 = sha256_digest(s)

    if isinstance(options.cache, str):
        cache_fn = options.cache
    else:
        if options.cache is not True:
            raise ConfigurationError("cache argument must be bool or str")

        try:
            username = getpass.getuser()
        except Exception:
            username = "unknown"

        cache_fn = tempfile.gettempdir() + "/.lark_%s_%s_%s_%s_%s.tmp" % (
            "cache_grammar" if options.cache_grammar else "cache", username, cache_sha256, *sys.version_info[:2])

    return cache_fn, cache_sha256


def load_from_cache(lark_instance, cache_fn: str, cache_sha256: str, options: Dict[str, Any]) -> bool:
    """Try to load a cached parser.

    Returns True if successful, False otherwise.
    """
    from .load_grammar import verify_used_files

    old_options = lark_instance.options
    try:
        with FS.open(cache_fn, 'rb') as f:
            logger.debug('Loading grammar from cache: %s', cache_fn)
            # Remove options that aren't relevant for loading from cache
            for name in (set(options) - _LOAD_ALLOWED_OPTIONS):
                del options[name]
            file_sha256 = f.readline().rstrip(b'\n')
            cached_used_files = pickle.load(f)
            if file_sha256 == cache_sha256.encode('utf8') and verify_used_files(cached_used_files):
                cached_parser_data = pickle.load(f)
                lark_load_into(lark_instance, cached_parser_data, **options)
                return True
    except FileNotFoundError:
        # The cache file doesn't exist; parse and compose the grammar as normal
        pass
    except Exception: # We should probably narrow done which errors we catch here.
        logger.exception("Failed to load Lark from cache: %r. We will try to carry on.", cache_fn)

        # In theory, the Lark instance might have been messed up by the call to `_load`.
        # In practice the only relevant thing that might have been overwritten should be `options`
        lark_instance.options = old_options

    return False


def save_to_cache(cache_fn: str, cache_sha256: str, lark_instance, used_files) -> None:
    """Save the parser to cache."""
    logger.debug('Saving grammar to cache: %s', cache_fn)
    try:
        with FS.open(cache_fn, 'wb') as f:
            assert cache_sha256 is not None
            f.write(cache_sha256.encode('utf8') + b'\n')
            pickle.dump(used_files, f)
            lark_save(lark_instance, f, _LOAD_ALLOWED_OPTIONS)
    except IOError as e:
        logger.exception("Failed to save Lark to cache: %r.", cache_fn, e)
