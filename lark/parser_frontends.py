from .exceptions import ConfigurationError, GrammarError
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
    def __init__(self, parser, lexer):
        self.parser = parser
        self.lexer = lexer

    def __call__(self, lexer_conf, parser_conf, options):
        assert isinstance(lexer_conf, LexerConf)
        assert isinstance(parser_conf, ParserConf)
        parser_conf.name = self.parser
        lexer_conf.name = self.lexer
        return ParsingFrontend(lexer_conf, parser_conf, options)

    @classmethod
    def deserialize(cls, data, memo, callbacks, options):
        lexer_conf = LexerConf.deserialize(data['lexer_conf'], memo)
        parser_conf = ParserConf.deserialize(data['parser_conf'], memo)
        parser = LALR_Parser.deserialize(data['parser'], memo, callbacks, options.debug)
        parser_conf.callbacks = callbacks

        terminals = [item for item in memo.values() if isinstance(item, TerminalDef)]

        lexer_conf.callbacks = _get_lexer_callbacks(options.transformer, terminals)
        lexer_conf.re_module = regex if options.regex else re
        lexer_conf.use_bytes = options.use_bytes
        lexer_conf.g_regex_flags = options.g_regex_flags
        lexer_conf.skip_validation = True
        lexer_conf.postlex = options.postlex

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
                'earley': make_early,
                'cyk': CYK_FrontEnd,
            }[parser_conf.name]
            self.parser = create_parser(lexer_conf, parser_conf, options)

        # Set-up lexer
        self.skip_lexer = False
        if lexer_conf.name in ('dynamic', 'dynamic_complete'):
            self.skip_lexer = True
            return

        try:
            create_lexer = {
                'standard': create_traditional_lexer,
                'contextual': create_contextual_lexer,
            }[lexer_conf.name]
        except KeyError:
            assert issubclass(lexer_conf.name, Lexer), lexer_conf.name
            self.lexer = _wrap_lexer(lexer_conf.name)(lexer_conf)
        else:
            self.lexer = create_lexer(lexer_conf, self.parser, lexer_conf.postlex)

        if lexer_conf.postlex:
            self.lexer = PostLexConnector(self.lexer, lexer_conf.postlex)


    def _parse(self, start, input, *args):
        if start is None:
            start = self.parser_conf.start
            if len(start) > 1:
                raise ConfigurationError("Lark initialized with more than 1 possible start rule. Must specify which start rule to parse", start)
            start ,= start
        return self.parser.parse(input, start, *args)

    def parse(self, text, start=None):
        if self.skip_lexer:
            return self._parse(start, text)

        lexer = LexerThread(self.lexer, text)
        return self._parse(start, lexer)


def get_frontend(parser, lexer):
    if parser=='lalr':
        if lexer is None:
            raise ConfigurationError('The LALR parser requires use of a lexer')
        if lexer not in ('standard' ,'contextual') and not issubclass(lexer, Lexer):
            raise ConfigurationError('Unknown lexer: %s' % lexer)
    elif parser=='earley':
        if lexer=='contextual':
            raise ConfigurationError('The Earley parser does not support the contextual parser')
    elif parser == 'cyk':
        if lexer != 'standard':
            raise ConfigurationError('CYK parser requires using standard parser.')
    else:
        raise ConfigurationError('Unknown parser: %s' % parser)

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


make_early = NotImplemented
CYK_FrontEnd = NotImplemented
###}

class EarleyRegexpMatcher:
    def __init__(self, lexer_conf):
        self.regexps = {}
        for t in lexer_conf.tokens:
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


def make_xearley(lexer_conf, parser_conf, options=None, **kw):
        earley_matcher = EarleyRegexpMatcher(lexer_conf)
        return xearley.Parser(parser_conf, earley_matcher.match, ignore=lexer_conf.ignore, **kw)

def _match_earley_basic(term, token):
    return term.name == token.type

def make_early_basic(lexer_conf, parser_conf, options, **kw):
    return earley.Parser(parser_conf, _match_earley_basic, **kw)

def make_early(lexer_conf, parser_conf, options):
    resolve_ambiguity = options.ambiguity == 'resolve'
    debug = options.debug if options else False
    tree_class = options.tree_class or Tree if options.ambiguity != 'forest' else None

    extra = {}
    if lexer_conf.name == 'dynamic':
        f = make_xearley
    elif lexer_conf.name == 'dynamic_complete':
        extra['complete_lex'] =True
        f = make_xearley
    else:
        f = make_early_basic

    return f(lexer_conf, parser_conf, options, resolve_ambiguity=resolve_ambiguity, debug=debug, tree_class=tree_class, **extra)



class CYK_FrontEnd:
    def __init__(self, lexer_conf, parser_conf, options=None):
        self._analysis = GrammarAnalyzer(parser_conf)
        self.parser = cyk.Parser(parser_conf.rules)

        self.callbacks = parser_conf.callbacks

    def parse(self, lexer, start):
        tokens = list(lexer.lex(None))
        tree = self.parser.parse(tokens, start)
        return self._transform(tree)

    def _transform(self, tree):
        subtrees = list(tree.iter_subtrees())
        for subtree in subtrees:
            subtree.children = [self._apply_callback(c) if isinstance(c, Tree) else c for c in subtree.children]

        return self._apply_callback(tree)

    def _apply_callback(self, tree):
        return self.callbacks[tree.rule](tree.children)
