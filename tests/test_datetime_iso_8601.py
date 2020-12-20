from pathlib import Path

import pytest
from lark import Lark


@pytest.fixture
def grammar_dir() -> Path:
    test_dir = Path(__file__).parent
    root_dir = test_dir.parent
    grammar_dir = root_dir.joinpath("lark/grammars")
    assert grammar_dir.exists()
    return grammar_dir


@pytest.fixture
def datetime_iso_8601_grammar(grammar_dir: Path) -> str:
    grammar = grammar_dir.joinpath("datetime_iso_8601.lark")
    assert grammar.is_file()
    return grammar.read_text()


def test_load_grammar(datetime_iso_8601_grammar: str):
    Lark(grammar=datetime_iso_8601_grammar)


def test_parse_valid(datetime_iso_8601_grammar: str):
    parser = Lark(grammar=datetime_iso_8601_grammar)