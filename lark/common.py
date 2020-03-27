from .utils import Serialize
from .lexer import TerminalDef

###{standalone

class LexerConf(Serialize):
    __serialize_fields__ = 'tokens', 'ignore', 'g_regex_flags'
    __serialize_namespace__ = TerminalDef,

    def __init__(self, tokens, ignore=(), postlex=None, callbacks=None, g_regex_flags=0):
        self.tokens = tokens
        self.ignore = ignore
        self.postlex = postlex
        self.callbacks = callbacks or {}
        self.g_regex_flags = g_regex_flags

    def _deserialize(self):
        self.callbacks = {} # TODO

###}

class ParserConf:
    def __init__(self, rules, callbacks, start):
        assert isinstance(start, list)
        self.rules = rules
        self.callbacks = callbacks
        self.start = start


