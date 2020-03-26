from .utils import Serialize
from .lexer import TerminalDef

###{standalone

class LexerConf(Serialize):
    __serialize_fields__ = 'tokens', 'ignore', 'global_flags'
    __serialize_namespace__ = TerminalDef,

    def __init__(self, tokens, ignore=(), postlex=None, callbacks=None, global_flags=0):
        self.tokens = tokens
        self.ignore = ignore
        self.postlex = postlex
        self.callbacks = callbacks or {}
        self.global_flags = global_flags

    def _deserialize(self):
        self.callbacks = {} # TODO

###}

class ParserConf:
    def __init__(self, rules, callbacks, start):
        assert isinstance(start, list)
        self.rules = rules
        self.callbacks = callbacks
        self.start = start


