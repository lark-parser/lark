from typing import Set, Dict, Any

from lark import Token, Tree


class ParserPuppet(object):
    """
    Provides an interface to interactively step through the parser (LALR(1) only for now)

    Accessible via `UnexpectedToken.puppet` (raised by the parser on token error)
    """
    parser: Any
    parser_state: Any
    lexer_state: Any
    

    def feed_token(self, token: Token) -> Any: ...

    def exhaust_lexer(self) -> None: ...

    def feed_eof(self, last_token: Token = None) -> Any: ...

    def copy(self) -> ParserPuppet: ...
    
    def as_immutable(self) -> ImmutableParserPuppet: ...

    def pretty(self) -> str: ...

    def choices(self) -> Dict[str, Any]: ...

    def accepts(self) -> Set[str]: ...

    def resume_parse(self) -> Tree: ...


class ImmutableParserPuppet(ParserPuppet):
    result: Any = None

    def feed_token(self, token: Token) -> ImmutableParserPuppet: ...

    def exhaust_lexer(self) -> ImmutableParserPuppet: ...

    def feed_eof(self, last_token: Token = None) -> ImmutableParserPuppet: ...
