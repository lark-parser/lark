# Porting from pyparsing to Lark

This guide is for projects that already have a working parser built with
[pyparsing](https://pyparsing-docs.readthedocs.io/) and want to move it to
Lark incrementally.

The main change is architectural: pyparsing grammars are Python object graphs,
while Lark grammars are usually written as EBNF text. In return, Lark can build
a parse tree automatically, run different parser algorithms from the same
grammar, and keep grammar and tree-processing code separate.

One common early porting surprise is whitespace: pyparsing skips whitespace by
default, but Lark only ignores whitespace that the grammar explicitly declares
with `%ignore`.

## Porting checklist

1. **Choose one representative input** from the pyparsing parser's tests.
2. **Write the Lark grammar for only that input shape**, not the whole language.
3. **Parse to a tree first**, before adding a transformer.
4. **Move parse actions to a `Transformer`** once the tree shape is stable.
5. **Add the rest of the syntax gradually**, keeping each pyparsing test paired
   with an equivalent Lark test.

## pyparsing concepts and Lark equivalents

| pyparsing | Lark |
| --- | --- |
| `Literal("+")`, `Keyword("if")` | string terminals: `"+"`, `"if"` |
| `Word(alphas)`, `Word(nums)` | regex terminals: `/[a-zA-Z]+/`, `/\d+/` or `%import common.INT` |
| `expr + term` | sequence: `expr term` |
| `expr | term` / `MatchFirst` | alternatives usually become `expr | term` in a rule |
| `Optional(expr)` | `expr?` |
| `ZeroOrMore(expr)` | `expr*` |
| `OneOrMore(expr)` | `expr+` |
| `Group(expr)` | a named rule, for example `group: expr` |
| `Suppress(expr)` | anonymous literals such as `"="`, or underscore-prefixed terminals/rules whose values are not needed in the tree |
| `setParseAction(fn)` | `Transformer` or `Visitor` methods |
| `ignore(...)` | `%ignore ...` |
| `delimitedList(item)` | `item ("," item)*` |
| `Forward()` | recursive rules, for example `?expr: atom | expr "+" atom` |
| `Regex(r"...")` | regex terminals: `/.../` |
| `QuotedString(...)` | quoted-string terminals, often `%import common.ESCAPED_STRING` |
| `CaselessKeyword("if")` | case-insensitive literals: `"if"i` |
| `setResultsName("name")` | rule aliases such as `-> name`, or transformer method names |
| `infixNotation(...)` | precedence rules |

Unlike pyparsing's `MatchFirst`, Lark alternatives are not inherently ordered in
the same way: LALR resolves choices deterministically from the parse table, and
Earley uses ambiguity handling and priorities when needed. If a pyparsing grammar
relies on ordering to choose between overlapping expressions, make that choice
explicit with priorities or more specific rules when porting.

## Minimal example

A small pyparsing parser might look like this:

```python
from pyparsing import Group, OneOrMore, Word, alphas, nums

assignment = Group(Word(alphas) + "=" + Word(nums))
parser = OneOrMore(assignment)

print(parser.parse_string("width=10 height=20").as_list())
```

A direct Lark version separates the grammar from the processing step:

```python
from lark import Lark, Transformer, v_args

parser = Lark(r"""
    start: assignment+

    assignment: NAME "=" INT

    %import common.CNAME -> NAME
    %import common.INT
    %import common.WS
    %ignore WS
""", parser="lalr")

@v_args(inline=True)
class ToDict(Transformer):
    def assignment(self, name, value):
        return str(name), int(value)

    def start(self, *items):
        return dict(items)

print(ToDict().transform(parser.parse("width=10 height=20")))
```

Result:

```python
{'width': 10, 'height': 20}
```

## Port parse actions to transformers

pyparsing parse actions run while parsing. Lark usually keeps parsing and tree
processing separate:

```python
@v_args(inline=True)
class BuildConfig(Transformer):
    def assignment(self, name, value):
        return str(name), int(value)
```

This has two useful effects while porting:

- grammar bugs are easier to see, because you can inspect `parser.parse(text).pretty()`;
- transformation bugs are isolated from parsing bugs.

If your pyparsing parse action validates or normalizes tokens, move that logic to
the matching transformer method. If it only discards punctuation, prefer handling
that in the grammar with literals or underscore-prefixed helper rules.

## Replace `ignore()` with `%ignore`

pyparsing commonly uses `parser.ignore(...)` for comments or whitespace. In Lark,
ignored text is part of the grammar:

```python
parser = Lark(r"""
    start: assignment+
    assignment: NAME "=" INT

    COMMENT: /#[^\n]*/

    %import common.CNAME -> NAME
    %import common.INT
    %import common.WS
    %ignore WS
    %ignore COMMENT
""", parser="lalr")
```

Use `%ignore` for syntax that can appear between tokens. If comments are
meaningful to your application, do not ignore them; keep them as terminals and
process them with a transformer or lexer callback.

## Port delimited lists

For a pyparsing list such as:

```python
from pyparsing import delimitedList, Word, alphas

names = delimitedList(Word(alphas))
```

Use a recursive or repeated Lark rule:

```text
names: NAME ("," NAME)*
%import common.CNAME -> NAME
%ignore " "
```

If the comma should never appear in the final tree, keep it as a literal string.
If it carries meaning, promote it to a named terminal.

## Port operator precedence

pyparsing's `infixNotation` encodes precedence in a Python list. In Lark, spell
out precedence as layers of grammar rules:

```text
?expr: sum
?sum: product
    | sum "+" product   -> add
    | sum "-" product   -> sub
?product: atom
    | product "*" atom  -> mul
    | product "/" atom  -> div
?atom: NUMBER           -> number
     | "(" expr ")"

%import common.NUMBER
%import common.WS
%ignore WS
```

This keeps the tree shape explicit: the aliases after `->` become transformer
method names such as `add`, `sub`, and `number`.

## Use `scan()` when pyparsing searched inside larger text

Some pyparsing parsers are used with `scan_string()` to find matching snippets
inside text that is not fully parsed. For that use case, use `Lark.scan()`:

```python
from lark import Lark

parser = Lark(r"""
    start: assignment
    assignment: NAME "=" INT

    %import common.CNAME -> NAME
    %import common.INT
    %ignore " "
""", parser="lalr")

for match in parser.scan("before width=10, between height=20, after"):
    print(match.value)
```

`scan()` walks the input from left to right and yields matches for grammar
snippets, while skipping text that does not match. This is usually the closest
replacement for pyparsing code that intentionally searches inside log lines,
templates, prose, or mixed-format files.

## Suggested migration workflow

Keep the old and new parsers side by side until the Lark grammar covers the same
inputs:

```python
def test_lark_matches_pyparsing_fixture():
    text = "width=10 height=20"
    assert parse_with_lark(text) == parse_with_pyparsing(text)
```

Good first fixtures are:

- the smallest valid input;
- a valid input with whitespace and comments;
- the most common real-world input;
- one invalid input that should produce a useful error.

Once these match, continue porting feature by feature. Avoid translating every
pyparsing helper mechanically; a shorter Lark grammar with a clear transformer is
often easier to maintain than a one-to-one rewrite.
