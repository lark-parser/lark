# Classes Reference

This page details the important classes in Lark.

----

## lark.Lark

The Lark class is the main interface for the library. It's mostly a thin wrapper for the many different parsers, and for the tree constructor.

#### \_\_init\_\_(self, grammar, **options)

The Lark class accepts a grammar string or file object, and keyword options:

* **start** - A list of the rules in the grammar that begin the parse (Default: `["start"]`)

* **parser** - Decides which parser engine to use, "earley", "lalr" or "cyk". (Default: `"earley"`)

* **lexer** - Overrides default lexer, depending on parser.

* **transformer** - Applies the provided transformer instead of building a parse tree (only allowed with parser="lalr")

* **postlex** - Lexer post-processing (Default: `None`. only works when lexer is "standard" or "contextual")

* **ambiguity** (only relevant for earley and cyk)

     * "explicit" - Return all derivations inside an "_ambig" data node.

     * "resolve" - Let the parser choose the best derivation (greedy for tokens, non-greedy for rules. Default)

* **debug** - Display warnings (such as Shift-Reduce warnings for LALR)

* **keep_all_tokens** - Don't throw away any terminals from the tree (Default=`False`)

* **propagate_positions** - Propagate line/column count to tree nodes, at the cost of performance (default=`False`)

* **maybe_placeholders** - The `[]` operator returns `None` when not matched. Setting this to `False` makes it behave like the `?` operator, and return no value at all, which may be a little faster (default=`True`)

* **lexer_callbacks** - A dictionary of callbacks of type f(Token) -> Token, used to interface with the lexer Token generation. Only works with the standard and contextual lexers. See [Recipes](recipes.md) for more information.

#### parse(self, text)

Return a complete parse tree for the text (of type Tree)

If a transformer is supplied to `__init__`, returns whatever is the result of the transformation.

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
