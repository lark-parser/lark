from typing import Optional, Tuple


class RuleOptions:
    keep_all_tokens: bool
    expand1: bool
    priority: int
    template_source: Optional[str]
    empty_indices: Tuple[bool, ...]


class Symbol:
    name: str
    is_term: bool
