from warnings import warn

from .utils import Serialize
from .lexer import TerminalDef

###{standalone


class LexerConf(Serialize):
    __serialize_fields__ = 'terminals', 'ignore', 'g_regex_flags', 'use_bytes', 'lexer_type'
    __serialize_namespace__ = TerminalDef,

    def __init__(self, terminals, re_module, ignore=(), postlex=None, callbacks=None, g_regex_flags=0, skip_validation=False, use_bytes=False):
        self.terminals = terminals
        self.terminals_by_name = {t.name: t for t in self.terminals}
        assert len(self.terminals) == len(self.terminals_by_name)
        self.ignore = ignore
        self.postlex = postlex
        self.callbacks = callbacks or {}
        self.g_regex_flags = g_regex_flags
        self.re_module = re_module
        self.skip_validation = skip_validation
        self.use_bytes = use_bytes
        self.lexer_type = None

    @property
    def tokens(self):
        warn("LexerConf.tokens is deprecated. Use LexerConf.terminals instead", DeprecationWarning)
        return self.terminals

    def _deserialize(self):
        self.terminals_by_name = {t.name: t for t in self.terminals}



class ParserConf(Serialize):
    __serialize_fields__ = 'rules', 'start', 'parser_type'

    def __init__(self, rules, callbacks, start):
        assert isinstance(start, list)
        self.rules = rules
        self.callbacks = callbacks
        self.start = start

        self.parser_type = None

###}
