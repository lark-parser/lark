import lark
import pytest
from lark.exceptions import LexError, UnexpectedCharacters


def test_zero_width_terminal_in_dynamic_earley():
    grammar = r"""
        start: line+
        line: "+" /(.*)/ LF
        LF: /\n/
    """
    for lexer in ("dynamic", "dynamic_complete"):
        parser = lark.Lark(grammar, start="start", parser="earley", lexer=lexer)
        assert parser.parse("+\n") is not None
        assert parser.parse("+text\n") is not None
        assert parser.parse("+\n+text\n") is not None


def test_zero_width_lookahead_terminals_in_dynamic_earley():
    grammar = r"""
        !start: BEFORE "a" AFTER
        BEFORE: /(?=a)/
        AFTER: /(?=$)/
    """
    for lexer in ("dynamic", "dynamic_complete"):
        parser = lark.Lark(grammar, parser="earley", lexer=lexer)
        assert parser.parse("a").children == ["", "a", ""]


def test_zero_width_terminal_remains_unsupported_by_basic_lexer():
    grammar = r"""
        start: "+" /(.*)/ LF
        LF: /\n/
    """
    for parser in ("earley", "lalr"):
        with pytest.raises(LexError):
            lark.Lark(grammar, parser=parser, lexer="basic")

def test_dynamic_complete_zero_width_prefix():
    import lark
    grammar = r"""
    start: A "a"
    A: /a*/
    """
    p = lark.Lark(grammar, start="start", parser="earley", lexer="dynamic_complete")
    tree = p.parse("a")
    assert tree is not None


def test_dynamic_complete_zero_width_invalid_input_reports_character():
    grammar = r"""
    start: A "a"
    A: /a*/
    """
    parser = lark.Lark(grammar, parser="earley", lexer="dynamic_complete")
    with pytest.raises(UnexpectedCharacters) as exc_info:
        parser.parse("b")
    assert exc_info.value.pos_in_stream == 0

