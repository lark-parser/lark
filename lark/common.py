

from .utils import reraise

class LexerConf:
    def __init__(self, tokens, ignore=(), postlex=None, callbacks=None, on_error=reraise):
        self.tokens = tokens
        self.ignore = ignore
        self.postlex = postlex
        self.callbacks = callbacks or {}
        self.on_error = on_error

class ParserConf:
    def __init__(self, rules, callback, start):
        self.rules = rules
        self.callback = callback
        self.start = start


