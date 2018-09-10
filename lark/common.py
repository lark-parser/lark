

class LexerConf:
    def __init__(self, tokens, ignore=(), postlex=None, callbacks=None):
        self.tokens = tokens
        self.ignore = ignore
        self.postlex = postlex
        self.callbacks = callbacks or {}

class ParserConf:
    def __init__(self, rules, callback, start):
        self.rules = rules
        self.callback = callback
        self.start = start


