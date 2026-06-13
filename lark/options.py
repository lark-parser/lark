"""Lark parser options.

Contains the LarkOptions class that specifies configuration for Lark parsers.
"""

from typing import Dict, Any, Union, Optional, Callable, List

from .exceptions import ConfigurationError, assert_config
from .serialize import Serialize

if False:
    from .lexer import TerminalDef
    from .grammar import Rule


class LarkOptions(Serialize):
    """Specifies the options for Lark

    """

    start: List[str]
    debug: bool
    strict: bool
    transformer: 'Optional[Any]'
    propagate_positions: Union[bool, str]
    maybe_placeholders: bool
    cache: Union[bool, str]
    cache_grammar: bool
    regex: bool
    g_regex_flags: int
    keep_all_tokens: bool
    tree_class: Optional[Callable[[str, List], Any]]
    parser: Any
    lexer: Any
    ambiguity: str
    postlex: Optional[Any]
    priority: 'Optional[str]'
    lexer_callbacks: Dict[str, Callable]
    use_bytes: bool
    ordered_sets: bool
    edit_terminals: Optional[Callable]
    import_paths: List
    source_path: Optional[str]

    OPTIONS_DOC = r"""
    **===  General Options  ===**

    start
            The start symbol. Either a string, or a list of strings for multiple possible starts (Default: "start")
    debug
            Display debug information and extra warnings. Use only when debugging (Default: ``False``)
            When used with Earley, it generates a forest graph as "sppf.png", if 'dot' is installed.
    strict
            Throw an exception on any potential ambiguity, including shift/reduce conflicts, and regex collisions.
    transformer
            Applies the transformer to every parse tree (equivalent to applying it after the parse, but faster)
    propagate_positions
            Propagates positional attributes into the 'meta' attribute of all tree branches.
            Sets attributes: (line, column, end_line, end_column, start_pos, end_pos,
                              container_line, container_column, container_end_line, container_end_column)
            Accepts ``False``, ``True``, or a callable, which will filter which nodes to ignore when propagating.
    maybe_placeholders
            When ``True``, the ``[]`` operator returns ``None`` when not matched.
            When ``False``,  ``[]`` behaves like the ``?`` operator, and returns no value at all.
            (default= ``True``)
    cache
            Cache the results of the Lark grammar analysis, for x2 to x3 faster loading. LALR only for now.

            - When ``False``, does nothing (default)
            - When ``True``, caches to a temporary file in the local directory
            - When given a string, caches to the path pointed by the string
    cache_grammar
            For use with ``cache`` option. When ``True``, the unanalyzed grammar is also included in the cache.
            Useful for classes that require the ``Lark.grammar`` to be present (e.g. Reconstructor).
            (default= ``False``)
    regex
            When True, uses the ``regex`` module instead of the stdlib ``re``.
    g_regex_flags
            Flags that are applied to all terminals (both regex and strings)
    keep_all_tokens
            Prevent the tree builder from automagically removing "punctuation" tokens (Default: ``False``)
    tree_class
            Lark will produce trees comprised of instances of this class instead of the default ``lark.Tree``.

    **=== Algorithm Options ===**

    parser
            Decides which parser engine to use. Accepts "earley" or "lalr". (Default: "earley").
            (there is also a "cyk" option for legacy)
    lexer
            Decides whether or not to use a lexer stage

            - "auto" (default): Choose for me based on the parser
            - "basic": Use a basic lexer
            - "contextual": Stronger lexer (only works with parser="lalr")
            - "dynamic": Flexible and powerful (only with parser="earley")
            - "dynamic_complete": Same as dynamic, but tries *every* variation of tokenizing possible.
    ambiguity
            Decides how to handle ambiguity in the parse. Only relevant if parser="earley"

            - "resolve": The parser will automatically choose the simplest derivation
              (it chooses consistently: greedy for tokens, non-greedy for rules)
            - "explicit": The parser will return all derivations wrapped in "_ambig" tree nodes (i.e. a forest).
            - "forest": The parser will return the root of the shared packed parse forest.

    **=== Misc. / Domain Specific Options ===**

    postlex
            Lexer post-processing (Default: ``None``) Only works with the basic and contextual lexers.
    priority
            How priorities should be evaluated - "auto", ``None``, "normal", "invert" (Default: "auto")
    lexer_callbacks
            Dictionary of callbacks for the lexer. May alter tokens during lexing. Use with caution.
    use_bytes
            Accept an input of type ``bytes`` instead of ``str``.
    ordered_sets
            Should Earley use ordered-sets to achieve stable output (~10% slower than regular sets. Default: True)
    edit_terminals
            A callback for editing the terminals before parse.
    import_paths
            A List of either paths or loader functions to specify from where grammars are imported
    source_path
            Override the source of from where the grammar was loaded. Useful for relative imports and unconventional grammar loading
    **=== End of Options ===**
    """

    # Adding a new option needs to be done in multiple places:
    # - In the dictionary below. This is the primary truth of which options `Lark.__init__` accepts
    # - In the docstring above. It is used both for the docstring of `LarkOptions` and `Lark`, and in readthedocs
    # - As an attribute of `LarkOptions` above
    # - Potentially in `_LOAD_ALLOWED_OPTIONS` below this class, when the option doesn't change how the grammar is loaded
    # - Potentially in `lark.tools.__init__`, if it makes sense, and it can easily be passed as a cmd argument
    _defaults: Dict[str, Any] = {
        'debug': False,
        'strict': False,
        'keep_all_tokens': False,
        'tree_class': None,
        'cache': False,
        'cache_grammar': False,
        'postlex': None,
        'parser': 'earley',
        'lexer': 'auto',
        'transformer': None,
        'start': 'start',
        'priority': 'auto',
        'ambiguity': 'auto',
        'regex': False,
        'propagate_positions': False,
        'lexer_callbacks': {},
        'maybe_placeholders': True,
        'edit_terminals': None,
        'g_regex_flags': 0,
        'use_bytes': False,
        'ordered_sets': True,
        'import_paths': [],
        'source_path': None,
        '_plugins': {},
    }

    def __init__(self, options_dict: Dict[str, Any]) -> None:
        o = dict(options_dict)

        options = {}
        for name, default in self._defaults.items():
            if name in o:
                value = o.pop(name)
                if isinstance(default, bool) and name not in ('cache', 'use_bytes', 'propagate_positions'):
                    value = bool(value)
            else:
                value = default

            options[name] = value

        if isinstance(options['start'], str):
            options['start'] = [options['start']]

        self.__dict__['options'] = options


        assert_config(self.parser, ('earley', 'lalr', 'cyk', None))

        if self.parser == 'earley' and self.transformer:
            raise ConfigurationError('Cannot specify an embedded transformer when using the Earley algorithm. '
                             'Please use your transformer on the resulting parse tree, or use a different algorithm (i.e. LALR)')

        if self.cache_grammar and not self.cache:
            raise ConfigurationError('cache_grammar cannot be set when cache is disabled')

        if o:
            raise ConfigurationError("Unknown options: %s" % o.keys())

    def __getattr__(self, name: str) -> Any:
        try:
            return self.__dict__['options'][name]
        except KeyError as e:
            raise AttributeError(e)

    def __setattr__(self, name: str, value: str) -> None:
        assert_config(name, self.options.keys(), "%r isn't a valid option. Expected one of: %s")
        self.options[name] = value

    def serialize(self, memo = None) -> Dict[str, Any]:
        return self.options

    @classmethod
    def deserialize(cls, data: Dict[str, Any], memo: Dict[int, Any]) -> "LarkOptions":
        return cls(data)


# Options that can be passed to the Lark parser, even when it was loaded from cache/standalone.
# These options are only used outside of `load_grammar`.
_LOAD_ALLOWED_OPTIONS = {'postlex', 'transformer', 'lexer_callbacks', 'use_bytes', 'debug', 'g_regex_flags', 'regex', 'propagate_positions', 'tree_class', '_plugins'}

_VALID_PRIORITY_OPTIONS = ('auto', 'normal', 'invert', None)
_VALID_AMBIGUITY_OPTIONS = ('auto', 'resolve', 'explicit', 'forest')
