from typing import Set, Dict, Any

from lark import Token, Tree


class ParserPuppet(object):
    """
    Provides an interface to interactively step through the parser (LALR(1) only for now)

    Accessible via `UnexpectedToken.puppet` (raised by the parser on token error)
    """
    def feed_token(self, token: Token): ...

    def copy(self) -> ParserPuppet: ...

    def pretty(self) -> str: ...

    def choices(self) -> Dict[str, Any]: ...

    def accepts(self) -> Set[str]: ...

    def resume_parse(self) -> Tree: ...
