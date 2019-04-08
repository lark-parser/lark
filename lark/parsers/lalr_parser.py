"""This module implements a LALR(1) Parser
"""
# Author: Erez Shinan (2017)
# Email : erezshin@gmail.com
from ..exceptions import UnexpectedToken
from ..lexer import Token
from ..grammar import Rule
from ..utils import Enumerator

from .lalr_analysis import LALR_Analyzer, Shift, Reduce, IntParseTable


class Parser(object):
    def __init__(self, parser_conf, debug=False):
        assert all(r.options is None or r.options.priority is None
                   for r in parser_conf.rules), "LALR doesn't yet support prioritization"
        analysis = LALR_Analyzer(parser_conf, debug=debug)
        analysis.compute_lookahead()
        callbacks = parser_conf.callbacks

        self._parse_table = analysis.parse_table
        self.parser_conf = parser_conf
        self.parser = _Parser(analysis.parse_table, callbacks)
        self.parse = self.parser.parse

    def serialize(self):
        tokens = Enumerator()
        rules = Enumerator()

        states = {
            state: {tokens.get(token): ((1, rules.get(arg)) if action is Reduce else (0, arg))
                    for token, (action, arg) in actions.items()}
            for state, actions in self._parse_table.states.items()
        }

        return {
            'tokens': tokens.reversed(),
            'rules': {idx: r.serialize() for idx, r in rules.reversed().items()},
            'states': states,
            'start_state': self._parse_table.start_state,
            'end_state': self._parse_table.end_state,
        }
    
    @classmethod
    def deserialize(cls, data, callbacks):
        tokens = data['tokens']
        rules = {idx: Rule.deserialize(r) for idx, r in data['rules'].items()}
        states = {
            state: {tokens[token]: ((Reduce, rules[arg]) if action==1 else (Shift, arg))
                    for token, (action, arg) in actions.items()}
            for state, actions in data['states'].items()
        }
        parse_table = IntParseTable(states, data['start_state'], data['end_state'])
        inst = cls.__new__(cls)
        inst.parser = _Parser(parse_table, callbacks)
        inst.parse = inst.parser.parse
        return inst



###{standalone

class _Parser:
    def __init__(self, parse_table, callbacks):
        self.states = parse_table.states
        self.start_state = parse_table.start_state
        self.end_state = parse_table.end_state
        self.callbacks = callbacks

    def parse(self, seq, set_state=None):
        token = None
        stream = iter(seq)
        states = self.states

        state_stack = [self.start_state]
        value_stack = []

        if set_state: set_state(self.start_state)

        def get_action(token):
            state = state_stack[-1]
            try:
                return states[state][token.type]
            except KeyError:
                expected = [s for s in states[state].keys() if s.isupper()]
                raise UnexpectedToken(token, expected, state=state)

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
        for token in stream:
            while True:
                action, arg = get_action(token)
                assert arg != self.end_state

                if action is Shift:
                    state_stack.append(arg)
                    value_stack.append(token)
                    if set_state: set_state(arg)
                    break # next token
                else:
                    reduce(arg)

        token = Token.new_borrow_pos('$END', '', token) if token else Token('$END', '', 0, 1, 1)
        while True:
            _action, arg = get_action(token)
            if _action is Shift:
                assert arg == self.end_state
                val ,= value_stack
                return val
            else:
                reduce(arg)

###}
