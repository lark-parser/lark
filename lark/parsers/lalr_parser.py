"""This module implements a LALR(1) Parser
"""
# Author: Erez Shinan (2017)
# Email : erezshin@gmail.com
import sys

from ..exceptions import SyntaxErrors, UnexpectedToken, UnexpectedCharacters
from ..tree import Tree
from ..lexer import Token
from ..utils import getLogger

from .. errors import parser_errors
from .lalr_analysis import LALR_Analyzer, Shift

log = getLogger(__name__)

class Parser:
    def __init__(self, parser_conf):
        assert all(r.options is None or r.options.priority is None
                   for r in parser_conf.rules), "LALR doesn't yet support prioritization"
        analysis = LALR_Analyzer(parser_conf)
        analysis.compute_lookahead()
        callbacks = {rule: getattr(parser_conf.callback, rule.alias or rule.origin, None)
                          for rule in parser_conf.rules}

        self._parse_table = analysis.parse_table
        self.parser_conf = parser_conf
        self.parser = _Parser(analysis.parse_table, callbacks)
        self.parse = self.parser.parse

###{standalone

class _Parser:
    def __init__(self, parse_table, callbacks):
        self.states = parse_table.states
        self.start_state = parse_table.start_state
        self.end_state = parse_table.end_state
        self.callbacks = callbacks
        self.error_reporting = False
        # TODO Verify whether `parser_errors` can be a member class atribute.
        # It depends on whether this is an member class object or static.
        # self.parser_errors = []

    def parse(self, seq, set_state=None):
        # stack of error contexts allowing this function to be reentrant
        # parser_errors = self.parser_errors
        parser_errors.append([])

        token = None
        stream = iter(seq)
        states = self.states

        state_stack = [self.start_state]
        value_stack = []

        if set_state: set_state(self.start_state)

        def get_action(key):
            state = state_stack[-1]
            try:
                return states[state][key]
            except KeyError:
                expected = [s for s in states[state].keys() if s.isupper()]
                exception = UnexpectedToken(token, expected, state=state)
                log(2, 'error_reporting %s, exception %s %s', self.error_reporting, type(exception), exception)

                if self.error_reporting:
                    raise exception

                else:
                    # TODO filter out rules from expected
                    parser_errors[-1].append(exception)

                    # Just take the first expected key
                    for s in states[state].keys():
                        if s.isupper():
                            log( 2, 'For %s and %s, returning key %s - %s', state, key, s, states[state][s] )
                            return states[state][s]

        def reduce(rule):
            size = len(rule.expansion)
            log(2, "rule: %s", rule)
            log(2, "rule.expansion: %s", rule.expansion)
            if size:
                s = value_stack[-size:]

                del state_stack[-size:]
                del value_stack[-size:]
            else:
                s = []

            value = self.callbacks[rule](s)
            log(2, "callbacks[rule](s): %s", value)

            _action, new_state = get_action(rule.origin.name)
            assert _action is Shift
            state_stack.append(new_state)
            value_stack.append(value)

        def print_partial_tree():
            delimiter = '\n--------------\n'
            for item in value_stack:
                if isinstance(item, Tree):
                    sys.stderr.write('\npartial tree:%s%s\n' % (delimiter, item.pretty()))
                else:
                    sys.stderr.write('\nloose token:%s%s\n' % (delimiter, repr(item)))

            sys.stderr.write(delimiter)

        def raise_parsing_errors():
            log(2, 'parser_errors(%s): %s', len(parser_errors), parser_errors)
            if parser_errors[-1]:
                error_messages = []
                error_exceptions = []
                for index, exception in enumerate(parser_errors[-1]):
                    # Comment out this if to show the duplicated error messages removed
                    if not index or index > 0 and exception != parser_errors[-1][index-1]:
                        error_exceptions.append(exception)
                        if type(exception) is UnexpectedCharacters:
                            error_messages.append('\nLexer error: %s' % exception)
                        elif type(exception) is UnexpectedToken:
                            error_messages.append('\nParser error: %s' % exception)
                print_partial_tree()
                raise SyntaxErrors(error_exceptions, ''.join( error_messages ))

        try:
            # Main LALR-parser loop
            log( 2, '' ); index = -1
            for token in stream:
                index += 1; x = token; log( 2, "[@%s,%s:%s=%s<%s>,%s:%s]", index, x.pos_in_stream, x.pos_in_stream+len(x.value)-1, repr(x.value), x.type, x.line, x.column )
                while True:
                    log( 2, 'token %s %s', type(token), repr(token))
                    action, arg = get_action(token.type)
                    if arg == self.end_state:
                        break
                    if action is Shift:
                        state_stack.append(arg)
                        value_stack.append(token)
                        if set_state: set_state(arg)
                        break # next token
                    else:
                        reduce(arg)

            token = Token.new_borrow_pos('<EOF>', token, token) if token else Token('<EOF>', '', 0, 1, 1)
            while True:
                _action, arg = get_action('$END')
                if _action is Shift:
                    if arg != self.end_state:
                        raise_parsing_errors()
                        assert arg == self.end_state
                    val ,= value_stack
                    return val
                else:
                    reduce(arg)

            raise_parsing_errors()

        finally:
            # unstack the current error context on finish
            parser_errors.pop()

###}
