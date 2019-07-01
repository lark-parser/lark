from .utils import Serialize
from .lexer import TerminalDef

###{standalone

class LexerConf(Serialize):
    __serialize_fields__ = 'tokens', 'ignore'
    __serialize_namespace__ = TerminalDef,

    def __init__(self, tokens, ignore=(), postlex=None, callbacks=None):
        self.tokens = tokens
        self.ignore = ignore
        self.postlex = postlex
        self.callbacks = callbacks or {}

    def _deserialize(self):
        self.callbacks = {} # TODO

###}

class ParserConf:
    def __init__(self, rules, callbacks, start):
        assert isinstance(start, list)
        self.rules = rules
        self.callbacks = callbacks
        self.start = start


