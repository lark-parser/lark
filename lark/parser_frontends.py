from .exceptions import ConfigurationError, GrammarError, assert_config
from .utils import get_regexp_width, Serialize
from .parsers.grammar_analysis import GrammarAnalyzer
from .lexer import LexerThread, TraditionalLexer, ContextualLexer, Lexer, Token, TerminalDef
from .parsers import earley, xearley, cyk
from .parsers.lalr_parser import LALR_Parser
from .tree import Tree
from .common import LexerConf, ParserConf
try:
    import regex
except ImportError:
    regex = None
import re

###{standalone

def _wrap_lexer(lexer_class):
    future_interface = getattr(lexer_class, '__future_interface__', False)
    if future_interface:
        return lexer_class
    else:
        class CustomLexerWrapper(Lexer):
            def __init__(self, lexer_conf):
                self.lexer = lexer_class(lexer_conf)
            def lex(self, lexer_state, parser_state):
                return self.lexer.lex(lexer_state.text)
        return CustomLexerWrapper


class MakeParsingFrontend:
    def __init__(self, parser_type, lexer_type):
        self.parser_type = parser_type
        self.lexer_type = lexer_type

    def __call__(self, lexer_conf, parser_conf, options):
        assert isinstance(lexer_conf, LexerConf)
        assert isinstance(parser_conf, ParserConf)
        parser_conf.parser_type = self.parser_type
        lexer_conf.lexer_type = self.lexer_type
        return ParsingFrontend(lexer_conf, parser_conf, options)

    @classmethod
    def deserialize(cls, data, memo, lexer_conf, callbacks, options):
        parser_conf = ParserConf.deserialize(data['parser_conf'], memo)
        parser = LALR_Parser.deserialize(data['parser'], memo, callbacks, options.debug)
        parser_conf.callbacks = callbacks
        return ParsingFrontend(lexer_conf, parser_conf, options, parser=parser)




class ParsingFrontend(Serialize):
    __serialize_fields__ = 'lexer_conf', 'parser_conf', 'parser', 'options'

    def __init__(self, lexer_conf, parser_conf, options, parser=None):
        self.parser_conf = parser_conf
        self.lexer_conf = lexer_conf
        self.options = options

        # Set-up parser
        if parser:  # From cache
            self.parser = parser
        else:
            create_parser = {
                'lalr': create_lalr_parser,
                'earley': create_earley_parser,
                'cyk': CYK_FrontEnd,
            }[parser_conf.parser_type]
            self.parser = create_parser(lexer_conf, parser_conf, options)

        # Set-up lexer
        lexer_type = lexer_conf.lexer_type
        self.skip_lexer = False
        if lexer_type in ('dynamic', 'dynamic_complete'):
            assert lexer_conf.postlex is None
            self.skip_lexer = True
            return

        try:
            create_lexer = {
                'standard': create_traditional_lexer,
                'contextual': create_contextual_lexer,
            }[lexer_type]
        except KeyError:
            assert issubclass(lexer_type, Lexer), lexer_type
            self.lexer = _wrap_lexer(lexer_type)(lexer_conf)
        else:
            self.lexer = create_lexer(lexer_conf, self.parser, lexer_conf.postlex)

        if lexer_conf.postlex:
            self.lexer = PostLexConnector(self.lexer, lexer_conf.postlex)
    
    def _verify_start(self, start=None):
        if start is None:
            start = self.parser_conf.start
            if len(start) > 1:
                raise ConfigurationError("Lark initialized with more than 1 possible start rule. Must specify which start rule to parse", start)
            start ,= start
        elif start not in self.parser_conf.start:
            raise ConfigurationError("Unknown start rule %s. Must be one of %r" % (start, self.parser_conf.start))
        return start

    def parse(self, text, start=None, on_error=None):
        start = self._verify_start(start)
        stream = text if self.skip_lexer else LexerThread(self.lexer, text)
        kw = {} if on_error is None else {'on_error': on_error}
        return self.parser.parse(stream, start, **kw)
    
    def parse_interactive(self, text=None, start=None):
        start = self._verify_start(start)
        if self.parser_conf.parser_type != 'lalr':
            raise ConfigurationError("parse_interactive() currently only works with parser='lalr' ")
        stream = text if self.skip_lexer else LexerThread(self.lexer, text)
        return self.parser.parse_interactive(stream, start)


def get_frontend(parser, lexer):
    assert_config(parser, ('lalr', 'earley', 'cyk'))
    if not isinstance(lexer, type):     # not custom lexer?
        expected = {
            'lalr': ('standard', 'contextual'),
            'earley': ('standard', 'dynamic', 'dynamic_complete'),
            'cyk': ('standard', ),
         }[parser]
        assert_config(lexer, expected, 'Parser %r does not support lexer %%r, expected one of %%s' % parser)

    return MakeParsingFrontend(parser, lexer)


def _get_lexer_callbacks(transformer, terminals):
    result = {}
    for terminal in terminals:
        callback = getattr(transformer, terminal.name, None)
        if callback is not None:
            result[terminal.name] = callback
    return result

class PostLexConnector:
    def __init__(self, lexer, postlexer):
        self.lexer = lexer
        self.postlexer = postlexer

    def make_lexer_state(self, text):
        return self.lexer.make_lexer_state(text)

    def lex(self, lexer_state, parser_state):
        i = self.lexer.lex(lexer_state, parser_state)
        return self.postlexer.process(i)



def create_traditional_lexer(lexer_conf, parser, postlex):
    return TraditionalLexer(lexer_conf)

def create_contextual_lexer(lexer_conf, parser, postlex):
    states = {idx:list(t.keys()) for idx, t in parser._parse_table.states.items()}
    always_accept = postlex.always_accept if postlex else ()
    return ContextualLexer(lexer_conf, states, always_accept=always_accept)

def create_lalr_parser(lexer_conf, parser_conf, options=None):
    debug = options.debug if options else False
    return LALR_Parser(parser_conf, debug=debug)


create_earley_parser = NotImplemented
CYK_FrontEnd = NotImplemented
###}

class EarleyRegexpMatcher:
    def __init__(self, lexer_conf):
        self.regexps = {}
        for t in lexer_conf.terminals:
            if t.priority != 1:
                raise GrammarError("Dynamic Earley doesn't support weights on terminals", t, t.priority)
            regexp = t.pattern.to_regexp()
            try:
                width = get_regexp_width(regexp)[0]
            except ValueError:
                raise GrammarError("Bad regexp in token %s: %s" % (t.name, regexp))
            else:
                if width == 0:
                    raise GrammarError("Dynamic Earley doesn't allow zero-width regexps", t)
            if lexer_conf.use_bytes:
                regexp = regexp.encode('utf-8')

            self.regexps[t.name] = lexer_conf.re_module.compile(regexp, lexer_conf.g_regex_flags)

    def match(self, term, text, index=0):
        return self.regexps[term.name].match(text, index)


def create_earley_parser__dynamic(lexer_conf, parser_conf, options=None, **kw):
        earley_matcher = EarleyRegexpMatcher(lexer_conf)
        return xearley.Parser(parser_conf, earley_matcher.match, ignore=lexer_conf.ignore, **kw)

def _match_earley_basic(term, token):
    return term.name == token.type

def create_earley_parser__basic(lexer_conf, parser_conf, options, **kw):
    return earley.Parser(parser_conf, _match_earley_basic, **kw)

def create_earley_parser(lexer_conf, parser_conf, options):
    resolve_ambiguity = options.ambiguity == 'resolve'
    debug = options.debug if options else False
    tree_class = options.tree_class or Tree if options.ambiguity != 'forest' else None

    extra = {}
    if lexer_conf.lexer_type == 'dynamic':
        f = create_earley_parser__dynamic
    elif lexer_conf.lexer_type == 'dynamic_complete':
        extra['complete_lex'] =True
        f = create_earley_parser__dynamic
    else:
        f = create_earley_parser__basic

    return f(lexer_conf, parser_conf, options, resolve_ambiguity=resolve_ambiguity, debug=debug, tree_class=tree_class, **extra)



class CYK_FrontEnd:
    def __init__(self, lexer_conf, parser_conf, options=None):
        self._analysis = GrammarAnalyzer(parser_conf)
        self.parser = cyk.Parser(parser_conf.rules)

        self.callbacks = parser_conf.callbacks

    def parse(self, lexer_thread, start):
        tokens = list(lexer_thread.lex(None))
        tree = self.parser.parse(tokens, start)
        return self._transform(tree)

    def _transform(self, tree):
        subtrees = list(tree.iter_subtrees())
        for subtree in subtrees:
            subtree.children = [self._apply_callback(c) if isinstance(c, Tree) else c for c in subtree.children]

        return self._apply_callback(tree)

    def _apply_callback(self, tree):
        return self.callbacks[tree.rule](tree.children)
