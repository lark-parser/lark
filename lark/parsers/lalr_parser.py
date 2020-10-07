"""This module implements a LALR(1) Parser
"""
# Author: Erez Shinan (2017)
# Email : erezshin@gmail.com
from ..exceptions import UnexpectedToken
from ..lexer import Token
from ..utils import Enumerator, Serialize

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


class _Parser:
    def __init__(self, parse_table, callbacks, debug=False):
        self.parse_table = parse_table
        self.callbacks = callbacks
        self.debug = debug

    def parse(self, seq, start, set_state=None, value_stack=None, state_stack=None):
        token = None
        stream = iter(seq)
        states = self.parse_table.states
        start_state = self.parse_table.start_states[start]
        end_state = self.parse_table.end_states[start]

        state_stack = state_stack or [start_state]
        value_stack = value_stack or []

        if set_state: set_state(start_state)

        def get_action(token):
            state = state_stack[-1]
            try:
                return states[state][token.type]
            except KeyError:
                expected = {s for s in states[state].keys() if s.isupper()}
                try:
                    puppet = ParserPuppet(self, state_stack, value_stack, start, stream, set_state)
                except NameError:   # For standalone parser
                    puppet = None
                raise UnexpectedToken(token, expected, state=state, puppet=puppet)

        def reduce(rule):
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

        # Main LALR-parser loop
        try:
            for token in stream:
                while True:
                    action, arg = get_action(token)
                    assert arg != end_state

                    if action is Shift:
                        state_stack.append(arg)
                        value_stack.append(token)
                        if set_state: set_state(arg)
                        break # next token
                    else:
                        reduce(arg)
        except Exception as e:
            if self.debug:
                print("")
                print("STATE STACK DUMP")
                print("----------------")
                for i, s in enumerate(state_stack):
                    print('%d)' % i , s)
                print("")

            raise

        token = Token.new_borrow_pos('$END', '', token) if token else Token('$END', '', 0, 1, 1)
        while True:
            _action, arg = get_action(token)
            assert(_action is Reduce)
            reduce(arg)
            if state_stack[-1] == end_state:
                return value_stack[-1]

###}

