## Transformers & Visitors

Transformers & Visitors provide a convenient interface to process the parse-trees that Lark returns.

They are used by inheriting from the correct class (visitor or transformer), and implementing methods corresponding to the rule you wish to process. Each method accepts the children as an argument. That can be modified using the `v_args` decorator, which allows to inline the arguments (akin to `*args`), or add the tree `meta` property as an argument.

See: <a href="https://github.com/lark-parser/lark/blob/master/lark/visitors.py">visitors.py</a>

### Visitors

Visitors visit each node of the tree, and run the appropriate method on it according to the node's data.

They work bottom-up, starting with the leaves and ending at the root of the tree.

**Example:**
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

They work bottom-up (or: depth-first), starting with the leaves and ending at the root of the tree.

Transformers can be used to implement map & reduce patterns.

Because nodes are reduced from leaf to root, at any point the callbacks may assume the children have already been transformed (if applicable).

Transformers can be chained into a new transformer by using multiplication.

`Transformer` can do anything `Visitor` can do, but because it reconstructs the tree, it is slightly less efficient.


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

All these classes implement the transformer interface:

- Transformer - Recursively transforms the tree. This is the one you probably want.
- Transformer_InPlace - Non-recursive. Changes the tree in-place instead of returning new instances
- Transformer_InPlaceRecursive - Recursive. Changes the tree in-place instead of returning new instances

### visit_tokens

By default, transformers only visit rules. `visit_tokens=True` will tell Transformer to visit tokens as well. This is a slightly slower alternative to `lexer_callbacks`, but it's easier to maintain and works for all algorithms (even when there isn't a lexer).

**Example:**

```python
class T(Transformer):
    INT = int
    NUMBER = float
    def NAME(self, name):
        return lookup_dict.get(name, name)


T(visit_tokens=True).transform(tree)
```


### v_args

`v_args` is a decorator.

By default, callback methods of transformers/visitors accept one argument: a list of the node's children. `v_args` can modify this behavior.

When used on a transformer/visitor class definition, it applies to all the callback methods inside it.

`v_args` accepts one of three flags:

- `inline` - Children are provided as `*args` instead of a list argument (not recommended for very long lists).
- `meta` - Provides two arguments: `children` and `meta` (instead of just the first)
- `tree` - Provides the entire tree as the argument, instead of the children.

**Examples:**

```python
@v_args(inline=True)
class SolveArith(Transformer):
    def add(self, left, right):
        return left + right


class ReverseNotation(Transformer_InPlace):
    @v_args(tree=True)
    def tree_node(self, tree):
        tree.children = tree.children[::-1]
```

### `__default__` and `__default_token__`
These are the functions that are called on if a function with a corresponding name has not been found.

- The `__default__` method has the signature `(data, children, meta)`, with `data` being the data attribute of the node. It defaults to reconstruct the Tree

- The `__default_token__` just takes the `Token` as an argument. It defaults to just return the argument.


### Discard

When raising the `Discard` exception in a transformer callback, that node is discarded and won't appear in the parent.


