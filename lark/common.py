from .utils import Serialize
from .lexer import TerminalDef

###{standalone

class LexerConf(Serialize):
    __serialize_fields__ = 'tokens', 'ignore', 'g_regex_flags', 'use_bytes'
    __serialize_namespace__ = TerminalDef,

    def __init__(self, tokens, re_module, ignore=(), postlex=None, callbacks=None, g_regex_flags=0, skip_validation=False, use_bytes=False):
        self.tokens = tokens    # TODO should be terminals
        self.ignore = ignore
        self.postlex = postlex
        self.callbacks = callbacks or {}
        self.g_regex_flags = g_regex_flags
        self.re_module = re_module
        self.skip_validation = skip_validation
        self.use_bytes = use_bytes

###}

class ParserConf:
    def __init__(self, rules, callbacks, start):
        assert isinstance(start, list)
        self.rules = rules
        self.callbacks = callbacks
        self.start = start


