# Classes - Reference

This page details the important classes in Lark.

----

## Lark

The Lark class is the main interface for the library. It's mostly a thin wrapper for the many different parsers, and for the tree constructor.

### Methods

#### \_\_init\_\_(self, grammar, **options)

The Lark class accepts a grammar string or file object, and keyword options:

* start - The symbol in the grammar that begins the parse (Default: `"start"`)

* parser - Decides which parser engine to use, "earley", "lalr" or "cyk". (Default: `"earley"`)

* lexer - Overrides default lexer.

* transformer - Applies the transformer instead of building a parse tree (only allowed with parser="lalr")

* postlex - Lexer post-processing (Default: None. only works when lexer is "standard" or "contextual")

* ambiguity (only relevant for earley and cyk)

     * "explicit" - Return all derivations inside an "_ambig" data node.

     * "resolve" - Let the parser choose the best derivation (greedy for tokens, non-greedy for rules. Default)

* debug - Display warnings (such as Shift-Reduce warnings for LALR)

* keep_all_tokens - Don't throw away any terminals from the tree (Default=False)

* propagate_positions - Propagate line/column count to tree nodes (default=False)

* lexer_callbacks - A dictionary of callbacks of type f(Token) -> Token, used to interface with the lexer Token generation. Only works with the standard and contextual lexers. See [Recipes](recipes.md) for more information.

#### parse(self, text)

Return a complete parse tree for the text (of type Tree)

If a transformer is supplied to `__init__`, returns whatever is the result of the transformation.

----

## Tree

The main tree class

### Properties

* `data` - The name of the rule or alias
* `children` - List of matched sub-rules and terminals
* `meta` - Line & Column numbers, if using `propagate_positions`

### Methods

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

## Transformers & Visitors


### Methods

#### get_context(text, span)

Returns a pretty string pinpointing the error in the text, with `span` amount of context characters around it.

(The parser doesn't hold a copy of the text it has to parse, so you have to provide it again)

#### match_examples(parse_fn, examples)

Allows you to detect what's wrong in the input text by matching against example errors.

Accepts the parse function (usually `lark_instance.parse`) and a dictionary of `{'example_string': value}`.

The function will iterate the dictionary until it finds a matching error, and return the corresponding value.

For an example usage, see: [examples/error_reporting_lalr.py](https://github.com/lark-parser/lark/blob/master/examples/error_reporting_lalr.py)
