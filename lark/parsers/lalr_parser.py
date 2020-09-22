"""This module implements a LALR(1) Parser
"""
# Author: Erez Shinan (2017)
# Email : erezshin@gmail.com
from copy import deepcopy
from ..exceptions import UnexpectedCharacters, UnexpectedInput, UnexpectedToken
from ..lexer import Token

from .lalr_analysis import LALR_Analyzer, Shift, Reduce, IntParseTable
from .lalr_puppet import ParserPuppet

###{standalone

class LALR_Parser(object):
    def __init__(self, parser_conf, debug=False):
        analysis = LALR_Analyzer(parser_conf, debug=debug)
        analysis.compute_lalr()
        callbacks = parser_conf.callbacks

        self._parse_table = analysis.parse_table
        self.parser_conf = parser_conf
        self.parser = _Parser(analysis.parse_table, callbacks, debug)

    @classmethod
    def deserialize(cls, data, memo, callbacks, debug=False):
        inst = cls.__new__(cls)
        inst._parse_table = IntParseTable.deserialize(data, memo)
        inst.parser = _Parser(inst._parse_table, callbacks, debug)
        return inst

    def serialize(self, memo):
        return self._parse_table.serialize(memo)

    def parse(self, *args):
        return self.parser.parse(*args)


class ParserState:
    __slots__ = 'parse_table', 'lexer', 'callbacks', 'start', 'state_stack', 'value_stack', 'start_state', 'end_state', 'states'

    def __init__(self, parse_table, lexer, callbacks, start, state_stack=None, value_stack=None):
        self.parse_table = parse_table

        self.start_state = self.parse_table.start_states[start]
        self.end_state = self.parse_table.end_states[start]
        self.states = self.parse_table.states

        self.lexer = lexer
        self.callbacks = callbacks
        self.start = start
        self.state_stack = state_stack or [self.start_state]
        self.value_stack = value_stack or []

    @property
    def position(self):
        return self.state_stack[-1]

    def __copy__(self):
        return type(self)(
            self.parse_table,
            self.lexer, # XXX copy
            self.callbacks,
            self.start,
            list(self.state_stack),
            deepcopy(self.value_stack),
        )

    def feed_token(self, token, is_end=False):
        state_stack = self.state_stack
        value_stack = self.value_stack
        states = self.states

        while True:
            state = state_stack[-1]
            try:
                action, arg = states[state][token.type]
            except KeyError:
                expected = {s for s in states[state].keys() if s.isupper()}
                raise UnexpectedToken(token, expected, state=state, puppet=None)

            assert arg != self.end_state

            if action is Shift:
                # shift once and return
                assert not is_end
                state_stack.append(arg)
                value_stack.append(token)
                return arg
            else:
                # reduce+shift as many times as necessary
                rule = arg
                size = len(rule.expansion)
                if size:
                    s = value_stack[-size:]
                    del state_stack[-size:]
                    del value_stack[-size:]
                else:
                    s = []

                value = self.callbacks[rule](s)

                _action, new_state = states[state_stack[-1]][rule.origin.name]
                assert _action is Shift
                state_stack.append(new_state)
                value_stack.append(value)

                if is_end and state_stack[-1] == self.end_state:
                    return value_stack[-1]

class _Parser:
    def __init__(self, parse_table, callbacks, debug=False):
        self.parse_table = parse_table
        self.callbacks = callbacks
        self.debug = debug

    def parse(self, lexer, start, value_stack=None, state_stack=None):
        parser_state = ParserState(self.parse_table, lexer, self.callbacks, start, state_stack, value_stack)
        return self.parse_from_state(parser_state)

    def parse_from_state(self, state):
        # Main LALR-parser loop
        try:
            token = None
            for token in state.lexer.lex(state):
                state.feed_token(token)

            token = Token.new_borrow_pos('$END', '', token) if token else Token('$END', '', 0, 1, 1)
            return state.feed_token(token, True)
        except UnexpectedInput as e:
            try:
                e.puppet = ParserPuppet(self, state, state.lexer)
            except NameError:
                pass
            if isinstance(e, UnexpectedCharacters):
                s = state.lexer.state
                p = s.line_ctr.char_pos
                s.line_ctr.feed(s.text[p:p+1])
            raise e
        except Exception as e:
            if self.debug:
                print("")
                print("STATE STACK DUMP")
                print("----------------")
                for i, s in enumerate(state.state_stack):
                    print('%d)' % i , s)
                print("")

            raise
###}

