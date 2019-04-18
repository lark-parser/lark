import re
from functools import partial

from .utils import get_regexp_width, Serialize
from .parsers.grammar_analysis import GrammarAnalyzer
from .lexer import TraditionalLexer, ContextualLexer, Lexer, Token
from .parsers import earley, xearley, cyk
from .parsers.lalr_parser import LALR_Parser
from .grammar import Rule
from .tree import Tree
from .common import LexerConf

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
            return partial(LALR_CustomLexer, lexer)
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




class WithLexer(Serialize):
    lexer = None
    parser = None
    lexer_conf = None

    __serialize_fields__ = 'parser', 'lexer_conf'
    __serialize_namespace__ = LexerConf,

    def __init__(self, lexer_conf, parser_conf, options=None):
        self.lexer_conf = lexer_conf
        self.postlex = lexer_conf.postlex

    @classmethod
    def deserialize(cls, data, memo, callbacks, postlex):
        inst = super(WithLexer, cls).deserialize(data, memo)
        inst.postlex = postlex
        inst.parser = LALR_Parser.deserialize(inst.parser, memo, callbacks)
        inst.init_lexer()
        return inst
    
    def _serialize(self, data, memo):
        data['parser'] = data['parser'].serialize(memo)

    def lex(self, text):
        stream = self.lexer.lex(text)
        return self.postlex.process(stream) if self.postlex else stream

    def parse(self, text):
        token_stream = self.lex(text)
        sps = self.lexer.set_parser_state
        return self.parser.parse(token_stream, *[sps] if sps is not NotImplemented else [])

    def init_traditional_lexer(self):
        self.lexer = TraditionalLexer(self.lexer_conf.tokens, ignore=self.lexer_conf.ignore, user_callbacks=self.lexer_conf.callbacks)

class LALR_WithLexer(WithLexer):
    def __init__(self, lexer_conf, parser_conf, options=None):
        debug = options.debug if options else False
        self.parser = LALR_Parser(parser_conf, debug=debug)
        WithLexer.__init__(self, lexer_conf, parser_conf, options)

        self.init_lexer()

    def init_lexer(self):
        raise NotImplementedError()

class LALR_TraditionalLexer(LALR_WithLexer):
    def init_lexer(self):
        self.init_traditional_lexer()

class LALR_ContextualLexer(LALR_WithLexer):
    def init_lexer(self):
        states = {idx:list(t.keys()) for idx, t in self.parser._parse_table.states.items()}
        always_accept = self.postlex.always_accept if self.postlex else ()
        self.lexer = ContextualLexer(self.lexer_conf.tokens, states,
                                     ignore=self.lexer_conf.ignore,
                                     always_accept=always_accept,
                                     user_callbacks=self.lexer_conf.callbacks)
###}

class LALR_CustomLexer(LALR_WithLexer):
    def __init__(self, lexer_cls, lexer_conf, parser_conf, options=None):
        pass    # TODO

    def init_lexer(self):
        self.lexer = lexer_cls(self.lexer_conf)

def tokenize_text(text):
    line = 1
    col_start_pos = 0
    for i, ch in enumerate(text):
        if '\n' in ch:
            line += ch.count('\n')
            col_start_pos = i + ch.rindex('\n')
        yield Token('CHAR', ch, line=line, column=i - col_start_pos)

class Earley(WithLexer):
    def __init__(self, lexer_conf, parser_conf, options=None):
        WithLexer.__init__(self, lexer_conf, parser_conf, options)
        self.init_traditional_lexer()

        resolve_ambiguity = options.ambiguity == 'resolve'
        self.parser = earley.Parser(parser_conf, self.match, resolve_ambiguity=resolve_ambiguity)

    def match(self, term, token):
        return term.name == token.type


class XEarley:
    def __init__(self, lexer_conf, parser_conf, options=None, **kw):
        self.token_by_name = {t.name:t for t in lexer_conf.tokens}

        self._prepare_match(lexer_conf)
        resolve_ambiguity = options.ambiguity == 'resolve'
        self.parser = xearley.Parser(parser_conf,
                                    self.match,
                                    ignore=lexer_conf.ignore,
                                    resolve_ambiguity=resolve_ambiguity,
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

            self.regexps[t.name] = re.compile(regexp)

    def parse(self, text):
        return self.parser.parse(text)

class XEarley_CompleteLex(XEarley):
    def __init__(self, *args, **kw):
        XEarley.__init__(self, *args, complete_lex=True, **kw)



class CYK(WithLexer):

    def __init__(self, lexer_conf, parser_conf, options=None):
        WithLexer.__init__(self, lexer_conf, parser_conf, options)
        self.init_traditional_lexer()

        self._analysis = GrammarAnalyzer(parser_conf)
        self._parser = cyk.Parser(parser_conf.rules, parser_conf.start)

        self.callbacks = parser_conf.callbacks

    def parse(self, text):
        tokens = list(self.lex(text))
        parse = self._parser.parse(tokens)
        parse = self._transform(parse)
        return parse

    def _transform(self, tree):
        subtrees = list(tree.iter_subtrees())
        for subtree in subtrees:
            subtree.children = [self._apply_callback(c) if isinstance(c, Tree) else c for c in subtree.children]

        return self._apply_callback(tree)

    def _apply_callback(self, tree):
        return self.callbacks[tree.rule](tree.children)

