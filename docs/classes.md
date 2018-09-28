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

Iterates over all the subtrees, never returning to the same node twice (Lark's parse-tree is actually a DAG)

#### \_\_eq\_\_, \_\_hash\_\_

Trees can be hashed and compared.

----

## Transformers & Visitors

Transformers & Visitors provide a convenient interface to process the parse-trees that Lark returns.

They are used by inheriting from the correct class (visitor or transformer), and implementing methods corresponding to the rule you wish to process. Each methods accepts the children as an argument. That can be modified using the `v-args` decorator, which allows to inline the arguments (akin to `*args`), or add the tree `meta` property as an argument.

See: https://github.com/lark-parser/lark/blob/master/lark/visitors.py

### Visitors

Visitors visit each node of the tree, and run the appropriate method on it according to the node's data.

They work bottom-up, starting with the leaves and ending at the root of the tree.

**Example**
```python
class IncreaseAllNumbers(Visitor):
  def number(self, tree):
    assert tree.data == "number"
    tree.children[0] += 1

IncreaseAllNumbers().visit(parse_tree)
```

There are two classes that implement the visitor interface:

* Visitor - Visit every node (without recursion)

* Visitor_Recursive - Visit every node using recursion. Slightly faster.

### Transformers

Transformers visit each node of the tree, and run the appropriate method on it according to the node's data.

They work bottom-up, starting with the leaves and ending at the root of the tree.

Transformers can be used to implement map & reduce patterns.

Because nodes are reduced from leaf to root, at any point the callbacks may assume the children have already been transformed (if applicable).

Transformers can be chained into a new transformer by using multiplication.

**Example:**
```python
from lark import Tree, Transformer

class EvalExpressions(Transformer):
    def expr(self, args):
            return eval(args[0])

t = Tree('a', [Tree('expr', ['1+2'])])
print(EvalExpressions().transform( t ))

# Prints: Tree(a, [3])
```


Here are the classes that implement the transformer interface:

- Transformer - Recursively transforms the tree. This is the one you probably want.
- Transformer_InPlace - Non-recursive. Changes the tree in-place instead of returning new instances
- Transformer_InPlaceRecursive - Recursive. Changes the tree in-place instead of returning new instances

### v_args

`v_args` is a decorator.

By default, callback methods of transformers/visitors accept one argument: a list of the node's children. `v_args` can modify this behavior.

When used on a transformer/visitor class definition, it applies to all the callback methods inside it.

`v_args` accepts one of three flags:

- `inline` - Children are provided as `*args` instead of a list argument (not recommended for very long lists).
- `meta` - Provides two arguments: `children` and `meta` (instead of just the first)
- `tree` - Provides the entire tree as the argument, instead of the children.

Examples:

```python
@v_args(inline=True)
class SolveArith(Transformer):
    def add(self, left, right):
        return left + right


class ReverseNotation(Transformer_InPlace):
    @v_args(tree=True):
    def tree_node(self, tree):
        tree.children = tree.children[::-1]
```

### Discard

When raising the `Discard` exception in a transformer callback, that node is discarded and won't appear in the parent.

## Token

When using a lexer, the resulting tokens in the trees will be of the Token class, which inherits from Python's string. So, normal string comparisons and operations will work as expected. Tokens also have other useful attributes:

* `type` - Name of the token (as specified in grammar).
* `pos_in_stream` - the index of the token in the text
* `line` - The line of the token in the text (starting with 1)
* `column` - The column of the token in the text (starting with 1)
* `end_line` - The line where the token ends
* `end_column` - The next column after the end of the token. For example, if the token is a single character with a `column` value of 4, `end_column` will be 5.


## UnexpectedInput

- `UnexpectedInput`
    - `UnexpectedToken` - The parser recieved an unexpected token
    - `UnexpectedCharacters` - The lexer encountered an unexpected string

After catching one of these exceptions, you may call the following helper methods to create a nicer error message:

### Methods

#### get_context(text, span)

Returns a pretty string pinpointing the error in the text, with `span` amount of context characters around it.

(The parser doesn't hold a copy of the text it has to parse, so you have to provide it again)

#### match_examples(parse_fn, examples)

Allows you to detect what's wrong in the input text by matching against example errors.

Accepts the parse function (usually `lark_instance.parse`) and a dictionary of `{'example_string': value}`.

The function will iterate the dictionary until it finds a matching error, and return the corresponding value.

For an example usage, see: [examples/error_reporting_lalr.py](https://github.com/lark-parser/lark/blob/master/examples/error_reporting_lalr.py)
