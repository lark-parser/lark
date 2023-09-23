"""This module implements a LALR(1) Parser
"""
# Author: Erez Shinan (2017)
# Email : erezshin@gmail.com
from copy import deepcopy, copy
from typing import Dict, Any, Generic, List, Optional
from ..lexer import Token, LexerThread
from ..utils import Serialize
from ..common import ParserConf, ParserCallbacks

from .lalr_analysis import LALR_Analyzer, Shift, IntParseTable, ParseTableBase, StateT
from .lalr_interactive_parser import InteractiveParser
from lark.exceptions import UnexpectedCharacters, UnexpectedInput, UnexpectedToken

###{standalone

class LALR_Parser(Serialize):
    def __init__(self, parser_conf: ParserConf, debug: bool=False, strict: bool=False):
        analysis = LALR_Analyzer(parser_conf, debug=debug, strict=strict)
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

    def serialize(self, memo: Any = None) -> Dict[str, Any]:
        return self._parse_table.serialize(memo)

    def parse_interactive(self, lexer: LexerThread, start: str):
        return self.parser.parse(lexer, start, start_interactive=True)

    def parse(self, lexer, start, on_error=None):
        try:
            return self.parser.parse(lexer, start)
        except UnexpectedInput as e:
            if on_error is None:
                raise

            while True:
                if isinstance(e, UnexpectedCharacters):
                    s = e.interactive_parser.lexer_thread.state
                    p = s.line_ctr.char_pos

                if not on_error(e):
                    raise e

                if isinstance(e, UnexpectedCharacters):
                    # If user didn't change the character position, then we should
                    if p == s.line_ctr.char_pos:
                        s.line_ctr.feed(s.text[p:p+1])

                try:
                    return e.interactive_parser.resume_parse()
                except UnexpectedToken as e2:
                    if (isinstance(e, UnexpectedToken)
                        and e.token.type == e2.token.type == '$END'
                        and e.interactive_parser == e2.interactive_parser):
                        # Prevent infinite loop
                        raise e2
                    e = e2
                except UnexpectedCharacters as e2:
                    e = e2


class ParseConf(Generic[StateT]):
    __slots__ = 'parse_table', 'callbacks', 'start', 'start_state', 'end_state', 'states'

    parse_table: ParseTableBase[StateT]
    callbacks: ParserCallbacks
    start: str

    start_state: StateT
    end_state: StateT
    states: Dict[StateT, Dict[str, tuple]]

    def __init__(self, parse_table: ParseTableBase[StateT], callbacks: ParserCallbacks, start: str):
        self.parse_table = parse_table

        self.start_state = self.parse_table.start_states[start]
        self.end_state = self.parse_table.end_states[start]
        self.states = self.parse_table.states

        self.callbacks = callbacks
        self.start = start


class ParserState(Generic[StateT]):
    __slots__ = 'parse_conf', 'lexer', 'state_stack', 'value_stack'

    parse_conf: ParseConf[StateT]
    lexer: LexerThread
    state_stack: List[StateT]
    value_stack: list

    def __init__(self, parse_conf: ParseConf[StateT], lexer: LexerThread, state_stack=None, value_stack=None):
        self.parse_conf = parse_conf
        self.lexer = lexer
        self.state_stack = state_stack or [self.parse_conf.start_state]
        self.value_stack = value_stack or []

    @property
    def position(self) -> StateT:
        return self.state_stack[-1]

    # Necessary for match_examples() to work
    def __eq__(self, other) -> bool:
        if not isinstance(other, ParserState):
            return NotImplemented
        return len(self.state_stack) == len(other.state_stack) and self.position == other.position

    def __copy__(self):
        return type(self)(
            self.parse_conf,
            self.lexer, # XXX copy
            copy(self.state_stack),
            deepcopy(self.value_stack),
        )

    def copy(self) -> 'ParserState[StateT]':
        return copy(self)

    def feed_token(self, token: Token, is_end=False) -> Any:
        state_stack = self.state_stack
        value_stack = self.value_stack
        states = self.parse_conf.states
        end_state = self.parse_conf.end_state
        callbacks = self.parse_conf.callbacks

        while True:
            state = state_stack[-1]
            try:
                action, arg = states[state][token.type]
            except KeyError:
                expected = {s for s in states[state].keys() if s.isupper()}
                raise UnexpectedToken(token, expected, state=self, interactive_parser=None)

            assert arg != end_state

            if action is Shift:
                # shift once and return
                assert not is_end
                state_stack.append(arg)
                value_stack.append(token if token.type not in callbacks else callbacks[token.type](token))
                return
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

                value = callbacks[rule](s) if callbacks else s

                _action, new_state = states[state_stack[-1]][rule.origin.name]
                assert _action is Shift
                state_stack.append(new_state)
                value_stack.append(value)

                if is_end and state_stack[-1] == end_state:
                    return value_stack[-1]

class _Parser:
    parse_table: ParseTableBase
    callbacks: ParserCallbacks
    debug: bool

    def __init__(self, parse_table: ParseTableBase, callbacks: ParserCallbacks, debug: bool=False):
        self.parse_table = parse_table
        self.callbacks = callbacks
        self.debug = debug

    def parse(self, lexer: LexerThread, start: str, value_stack=None, state_stack=None, start_interactive=False):
        parse_conf = ParseConf(self.parse_table, self.callbacks, start)
        parser_state = ParserState(parse_conf, lexer, state_stack, value_stack)
        if start_interactive:
            return InteractiveParser(self, parser_state, parser_state.lexer)
        return self.parse_from_state(parser_state)


    def parse_from_state(self, state: ParserState, last_token: Optional[Token]=None):
        """Run the main LALR parser loop

        Parameters:
            state - the initial state. Changed in-place.
            last_token - Used only for line information in case of an empty lexer.
        """
        try:
            token = last_token
            for token in state.lexer.lex(state):
                assert token is not None
                state.feed_token(token)

            end_token = Token.new_borrow_pos('$END', '', token) if token else Token('$END', '', 0, 1, 1)
            return state.feed_token(end_token, True)
        except UnexpectedInput as e:
            try:
                e.interactive_parser = InteractiveParser(self, state, state.lexer)
            except NameError:
                pass
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
