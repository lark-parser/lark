# Classes Reference

This page details the important classes in Lark.

----

## lark.Lark

The Lark class is the main interface for the library. It's mostly a thin wrapper for the many different parsers, and for the tree constructor.

#### \_\_init\_\_(self, grammar_string, **options)

Creates an instance of Lark with the given grammar

#### open(cls, grammar_filename, rel_to=None, **options)

Creates an instance of Lark with the grammar given by its filename

If rel_to is provided, the function will find the grammar filename in relation to it.

Example:

```python
    >>> Lark.open("grammar_file.lark", rel_to=__file__, parser="lalr")
    Lark(...)
```

#### parse(self, text)

Return a complete parse tree for the text (of type Tree)

If a transformer is supplied to `__init__`, returns whatever is the result of the transformation.


#### save(self, f) / load(cls, f)

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

**keep_all_tokens** - Prevent the tree builder from automagically removing "punctuation" tokens (default: False)

**cache_grammar** - Cache the Lark grammar (Default: False)

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

#### Domain Specific

- **postlex** - Lexer post-processing (Default: None) Only works with the standard and contextual lexers.
- **priority** - How priorities should be evaluated - auto, none, normal, invert (Default: auto)
- **lexer_callbacks** - Dictionary of callbacks for the lexer. May alter tokens during lexing. Use with caution.
- **edit_terminals** - A callback

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

## UnexpectedToken

## UnexpectedException

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
