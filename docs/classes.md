# Classes Reference

This page details the important classes in Lark.

----

## lark.Lark

The Lark class is the main interface for the library. It's mostly a thin wrapper for the many different parsers, and for the tree constructor.

#### Lark.\_\_init\_\_
```python
def __init__(self, grammar_string, **options): ...
```
Creates an instance of Lark with the given grammar

Example:

```python
    >>> Lark(r'''start: "foo" ''')
    Lark(...)
```

#### Lark.open
```python
def open(cls, grammar_filename, rel_to=None, **options): ...
```

Creates an instance of Lark with the grammar given by its filename

If rel_to is provided, the function will find the grammar filename in relation to it.

Example:

```python
    >>> Lark.open("grammar_file.lark", rel_to=__file__, parser="lalr")
    Lark(...)
```

#### Lark.parse

```python
def parse(self, text, start=None, on_error=None): ...
```

Parse the given text, according to the options provided.

Returns a complete parse tree for the text (of type Tree)

If a transformer is supplied to `__init__`, returns whatever is the result of the transformation.

Parameters:

* start: str - required if Lark was given multiple possible start symbols (using the start option).

* on_error: function - if provided, will be called on UnexpectedToken error. Return true to resume parsing. LALR only.

(See `examples/error_puppet.py` for an example of how to use `on_error`.)

Example:
```python
    >>> Lark(r'''start: "hello" " "+ /\w+/ ''').parse('hello kitty')
    Tree(start, [Token(__ANON_0, 'kitty')])
```

#### Lark.save / Lark.load
```python
def save(self, f): ...
def load(cls, f): ...
```

Useful for caching and multiprocessing.

`save` saves the instance into the given file object

`load` loads an instance from the given file object

####


### Lark Options
#### General options

**start** - The start symbol. Either a string, or a list of strings for multiple possible starts (Default: "start")

**debug** - Display debug information, such as warnings (default: False)

**transformer** - Applies the transformer to every parse tree (equivlent to applying it after the parse, but faster)

**propagate_positions** - Propagates (line, column, end_line, end_column) attributes into all tree branches.

**maybe_placeholders** -
- When True, the `[]` operator returns `None` when not matched.
- When `False`,  `[]` behaves like the `?` operator, and returns no value at all.
- (default=`False`. Recommended to set to `True`)

**g_regex_flags** - Flags that are applied to all terminals (both regex and strings)

**regex** - Use the `regex` library instead of the built-in `re` module (See below)

**keep_all_tokens** - Prevent the tree builder from automagically removing "punctuation" tokens (default: False)

**cache** - Cache the results of the Lark grammar analysis, for x2 to x3 faster loading. LALR only for now.
- When `False`, does nothing (default)
- When `True`, caches to a temporary file in the local directory
- When given a string, caches to the path pointed by the string

#### Algorithm

**parser** - Decides which parser engine to use, "earley" or "lalr". (Default: "earley")
            (there is also a "cyk" option for legacy)

**lexer** - Decides whether or not to use a lexer stage

- "auto" (default): Choose for me based on the parser
- "standard": Use a standard lexer
- "contextual": Stronger lexer (only works with parser="lalr")
- "dynamic": Flexible and powerful (only with parser="earley")
- "dynamic_complete": Same as dynamic, but tries *every* variation of tokenizing possible. (only with parser="earley")

**ambiguity** - Decides how to handle ambiguity in the parse. Only relevant if parser="earley"
- "resolve": The parser will automatically choose the simplest derivation (it chooses consistently: greedy for tokens, non-greedy for rules)
- "explicit": The parser will return all derivations wrapped in "_ambig" tree nodes (i.e. a forest).

#### Misc.

- **postlex** - Lexer post-processing (Default: None) Only works with the standard and contextual lexers.
- **priority** - How priorities should be evaluated - auto, none, normal, invert (Default: auto)
- **lexer_callbacks** - Dictionary of callbacks for the lexer. May alter tokens during lexing. Use with caution.
- **edit_terminals** - A callback


#### Using Unicode character classes with `regex`
Python's builtin `re` module has a few persistent known bugs and also won't parse
advanced regex features such as character classes.
With `pip install lark-parser[regex]`, the `regex` module will be installed alongside `lark`
and can act as a drop-in replacement to `re`.

Any instance of `Lark` instantiated with `regex=True` will now use the `regex` module
instead of `re`. For example, we can now use character classes to match PEP-3131 compliant Python identifiers.
```python
from lark import Lark
>>> g = Lark(r"""
                    ?start: NAME
                    NAME: ID_START ID_CONTINUE*
                    ID_START: /[\p{Lu}\p{Ll}\p{Lt}\p{Lm}\p{Lo}\p{Nl}_]+/
                    ID_CONTINUE: ID_START | /[\p{Mn}\p{Mc}\p{Nd}\p{Pc}·]+/
                """, regex=True)

>>> g.parse('வணக்கம்')
'வணக்கம்'

```
----

## Tree

The main tree class

* `data` - The name of the rule or alias
* `children` - List of matched sub-rules and terminals
* `meta` - Line & Column numbers (if `propagate_positions` is enabled)
    * meta attributes: `line`, `column`, `start_pos`, `end_line`, `end_column`, `end_pos`

#### \_\_init\_\_(self, data, children)

Creates a new tree, and stores "data" and "children" in attributes of the same name.

#### pretty(self, indent_str='  ')

Returns an indented string representation of the tree. Great for debugging.

#### find_pred(self, pred)

Returns all nodes of the tree that evaluate pred(node) as true.

#### find_data(self, data)

Returns all nodes of the tree whose data equals the given data.

#### iter_subtrees(self)

Depth-first iteration.

Iterates over all the subtrees, never returning to the same node twice (Lark's parse-tree is actually a DAG).

#### iter_subtrees_topdown(self)

Breadth-first iteration.

Iterates over all the subtrees, return nodes in order like pretty() does.

#### \_\_eq\_\_, \_\_hash\_\_

Trees can be hashed and compared.

----

## Token

When using a lexer, the resulting tokens in the trees will be of the Token class, which inherits from Python's string. So, normal string comparisons and operations will work as expected. Tokens also have other useful attributes:

* `type` - Name of the token (as specified in grammar).
* `pos_in_stream` - the index of the token in the text
* `line` - The line of the token in the text (starting with 1)
* `column` - The column of the token in the text (starting with 1)
* `end_line` - The line where the token ends
* `end_column` - The next column after the end of the token. For example, if the token is a single character with a `column` value of 4, `end_column` will be 5.
* `end_pos` - the index where the token ends (basically pos_in_stream + len(token))

## Transformer
## Visitor
## Interpreter

See the [visitors page](visitors.md)


## UnexpectedInput

- `UnexpectedInput`
    - `UnexpectedToken` - The parser recieved an unexpected token
    - `UnexpectedCharacters` - The lexer encountered an unexpected string

After catching one of these exceptions, you may call the following helper methods to create a nicer error message:

#### get_context(text, span)

Returns a pretty string pinpointing the error in the text, with `span` amount of context characters around it.

(The parser doesn't hold a copy of the text it has to parse, so you have to provide it again)

#### match_examples(parse_fn, examples)

Allows you to detect what's wrong in the input text by matching against example errors.

Accepts the parse function (usually `lark_instance.parse`) and a dictionary of `{'example_string': value}`.

The function will iterate the dictionary until it finds a matching error, and return the corresponding value.

For an example usage, see: [examples/error_reporting_lalr.py](https://github.com/lark-parser/lark/blob/master/examples/error_reporting_lalr.py)


### UnexpectedToken

When the parser throws UnexpectedToken, it instanciates a puppet with its internal state.

Users can then interactively set the puppet to the desired puppet state, and resume regular parsing.

See [ParserPuppet](#ParserPuppet)

### UnexpectedCharacters

## ParserPuppet

ParserPuppet gives you advanced control over error handling when parsing with LALR.

For a simpler, more streamlined interface, see the `on_error` argument to `Lark.parse()`.

#### choices(self)

Returns a dictionary of token types, matched to their action in the parser.

Only returns token types that are accepted by the current state.

Updated by `feed_token()`

#### feed_token(self, token)

Feed the parser with a token, and advance it to the next state, as if it recieved it from the lexer.

Note that `token` has to be an instance of `Token`.

#### copy(self)

Create a new puppet with a separate state. Calls to `feed_token()` won't affect the old puppet, and vice-versa.

#### pretty(self)

Print the output of `choices()` in a way that's easier to read.

#### resume_parse(self)
Resume parsing from the current puppet state.

