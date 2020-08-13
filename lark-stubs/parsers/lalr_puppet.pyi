from typing import Set, Dict, Any

from lark import Token, Tree


class ParserPuppet(object):
    """
    Represents a LalrParser that can be step through.
    Shouldn't instantiated by hand, but is accessible as `UnexpectedToken.puppet`
    """
    def feed_token(self, token: Token): ...

    def copy(self) -> ParserPuppet: ...

    def pretty(self) -> str: ...

    def choices(self) -> Dict[str, Any]: ...

    def accepts(self) -> Set[str]: ...

    def resume_parse(self) -> Tree: ...
