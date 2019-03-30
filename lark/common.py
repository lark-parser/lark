

class LexerConf:
    def __init__(self, tokens, ignore=(), postlex=None, callbacks=None):
        self.tokens = tokens
        self.ignore = ignore
        self.postlex = postlex
        self.callbacks = callbacks or {}

class ParserConf:
    def __init__(self, rules, callbacks, start):
        self.rules = rules
        self.callbacks = callbacks
        self.start = start


