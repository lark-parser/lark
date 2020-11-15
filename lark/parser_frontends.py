from .utils import get_regexp_width, Serialize
from .parsers.grammar_analysis import GrammarAnalyzer
from .lexer import LexerThread, TraditionalLexer, ContextualLexer, Lexer, Token, TerminalDef
from .parsers import earley, xearley, cyk
from .parsers.lalr_parser import LALR_Parser
from .grammar import Rule
from .tree import Tree
from .common import LexerConf
try:
    import regex
except ImportError:
    regex = None
import re

###{standalone

def get_frontend(parser, lexer):
    if parser=='lalr':
        if lexer is None:
            raise ValueError('The LALR parser requires use of a lexer')
        elif lexer == 'standard':
            return LALR_TraditionalLexer
        elif lexer == 'contextual':
            return LALR_ContextualLexer
        elif issubclass(lexer, Lexer):
            class CustomLexerWrapper(Lexer):
                def __init__(self, lexer_conf):
                    self.lexer = lexer(lexer_conf)
                def lex(self, lexer_state, parser_state):
                    return self.lexer.lex(lexer_state.text)

            class LALR_CustomLexerWrapper(LALR_WithLexer):
                def __init__(self, lexer_conf, parser_conf, options=None):
                    super(LALR_CustomLexerWrapper, self).__init__(lexer_conf, parser_conf, options=options)
                def init_lexer(self):
                    future_interface = getattr(lexer, '__future_interface__', False)
                    if future_interface:
                        self.lexer = lexer(self.lexer_conf)
                    else:
                        self.lexer = CustomLexerWrapper(self.lexer_conf)

            return LALR_CustomLexerWrapper
        else:
            raise ValueError('Unknown lexer: %s' % lexer)
    elif parser=='earley':
        if lexer=='standard':
            return Earley
        elif lexer=='dynamic':
            return XEarley
        elif lexer=='dynamic_complete':
            return XEarley_CompleteLex
        elif lexer=='contextual':
            raise ValueError('The Earley parser does not support the contextual parser')
        else:
            raise ValueError('Unknown lexer: %s' % lexer)
    elif parser == 'cyk':
        if lexer == 'standard':
            return CYK
        else:
            raise ValueError('CYK parser requires using standard parser.')
    else:
        raise ValueError('Unknown parser: %s' % parser)


class _ParserFrontend(Serialize):
    def _parse(self, start, input, *args):
        if start is None:
            start = self.start
            if len(start) > 1:
                raise ValueError("Lark initialized with more than 1 possible start rule. Must specify which start rule to parse", start)
            start ,= start
        return self.parser.parse(input, start, *args)


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


class WithLexer(_ParserFrontend):
    lexer = None
    parser = None
    lexer_conf = None
    start = None

    __serialize_fields__ = 'parser', 'lexer_conf', 'start'
    __serialize_namespace__ = LexerConf,

    def __init__(self, lexer_conf, parser_conf, options=None):
        self.lexer_conf = lexer_conf
        self.start = parser_conf.start
        self.postlex = lexer_conf.postlex

    @classmethod
    def deserialize(cls, data, memo, callbacks, options):
        inst = super(WithLexer, cls).deserialize(data, memo)

        inst.postlex = options.postlex
        inst.parser = LALR_Parser.deserialize(inst.parser, memo, callbacks, options.debug)

        terminals = [item for item in memo.values() if isinstance(item, TerminalDef)]
        inst.lexer_conf.callbacks = _get_lexer_callbacks(options.transformer, terminals)
        inst.lexer_conf.re_module = regex if options.regex else re
        inst.lexer_conf.use_bytes = options.use_bytes
        inst.lexer_conf.g_regex_flags = options.g_regex_flags
        inst.lexer_conf.skip_validation = True
        inst.init_lexer()

        return inst

    def _serialize(self, data, memo):
        data['parser'] = data['parser'].serialize(memo)

    def make_lexer(self, text):
        lexer = self.lexer
        if self.postlex:
            lexer = PostLexConnector(self.lexer, self.postlex)
        return LexerThread(lexer, text)

    def parse(self, text, start=None):
        return self._parse(start, self.make_lexer(text))

    def init_traditional_lexer(self):
        self.lexer = TraditionalLexer(self.lexer_conf)

class LALR_WithLexer(WithLexer):
    def __init__(self, lexer_conf, parser_conf, options=None):
        debug = options.debug if options else False
        self.parser = LALR_Parser(parser_conf, debug=debug)
        WithLexer.__init__(self, lexer_conf, parser_conf, options)

        self.init_lexer()

    def init_lexer(self, **kw):
        raise NotImplementedError()

class LALR_TraditionalLexer(LALR_WithLexer):
    def init_lexer(self):
        self.init_traditional_lexer()

class LALR_ContextualLexer(LALR_WithLexer):
    def init_lexer(self):
        states = {idx:list(t.keys()) for idx, t in self.parser._parse_table.states.items()}
        always_accept = self.postlex.always_accept if self.postlex else ()
        self.lexer = ContextualLexer(self.lexer_conf, states, always_accept=always_accept)

###}


class Earley(WithLexer):
    def __init__(self, lexer_conf, parser_conf, options=None):
        WithLexer.__init__(self, lexer_conf, parser_conf, options)
        self.init_traditional_lexer()

        resolve_ambiguity = options.ambiguity == 'resolve'
        debug = options.debug if options else False
        tree_class = options.tree_class or Tree if options.ambiguity != 'forest' else None
        self.parser = earley.Parser(parser_conf, self.match, resolve_ambiguity=resolve_ambiguity, debug=debug, tree_class=tree_class)

    def make_lexer(self, text):
        return WithLexer.make_lexer(self, text).lex(None)

    def match(self, term, token):
        return term.name == token.type


class XEarley(_ParserFrontend):
    def __init__(self, lexer_conf, parser_conf, options=None, **kw):
        self.token_by_name = {t.name:t for t in lexer_conf.tokens}
        self.start = parser_conf.start

        self._prepare_match(lexer_conf)
        resolve_ambiguity = options.ambiguity == 'resolve'
        debug = options.debug if options else False
        tree_class = options.tree_class or Tree if options.ambiguity != 'forest' else None
        self.parser = xearley.Parser(parser_conf,
                                    self.match,
                                    ignore=lexer_conf.ignore,
                                    resolve_ambiguity=resolve_ambiguity,
                                    debug=debug,
                                    tree_class=tree_class,
                                    **kw
                                    )

    def match(self, term, text, index=0):
        return self.regexps[term.name].match(text, index)

    def _prepare_match(self, lexer_conf):
        self.regexps = {}
        for t in lexer_conf.tokens:
            if t.priority != 1:
                raise ValueError("Dynamic Earley doesn't support weights on terminals", t, t.priority)
            regexp = t.pattern.to_regexp()
            try:
                width = get_regexp_width(regexp)[0]
            except ValueError:
                raise ValueError("Bad regexp in token %s: %s" % (t.name, regexp))
            else:
                if width == 0:
                    raise ValueError("Dynamic Earley doesn't allow zero-width regexps", t)
            if lexer_conf.use_bytes:
                regexp = regexp.encode('utf-8')

            self.regexps[t.name] = lexer_conf.re_module.compile(regexp, lexer_conf.g_regex_flags)

    def parse(self, text, start):
        return self._parse(start, text)

class XEarley_CompleteLex(XEarley):
    def __init__(self, *args, **kw):
        XEarley.__init__(self, *args, complete_lex=True, **kw)



class CYK(WithLexer):

    def __init__(self, lexer_conf, parser_conf, options=None):
        WithLexer.__init__(self, lexer_conf, parser_conf, options)
        self.init_traditional_lexer()

        self._analysis = GrammarAnalyzer(parser_conf)
        self.parser = cyk.Parser(parser_conf.rules)

        self.callbacks = parser_conf.callbacks

    def parse(self, text, start):
        tokens = list(self.make_lexer(text).lex(None))
        parse = self._parse(start, tokens)
        parse = self._transform(parse)
        return parse

    def _transform(self, tree):
        subtrees = list(tree.iter_subtrees())
        for subtree in subtrees:
            subtree.children = [self._apply_callback(c) if isinstance(c, Tree) else c for c in subtree.children]

        return self._apply_callback(tree)

    def _apply_callback(self, tree):
        return self.callbacks[tree.rule](tree.children)
