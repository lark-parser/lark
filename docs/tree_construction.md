# Tree Construction Reference


Lark builds a tree automatically based on the structure of the grammar, where each rule that is matched becomes a branch (node) in the tree, and its children are its matches, in the order of matching.

For example, the rule `node: child1 child2` will create a tree node with two children. If it is matched as part of another rule (i.e. if it isn't the root), the new rule's tree node will become its parent.

Using `item+` or `item*` will result in a list of items, equivalent to writing `item item item ..`.

Using `item?` will return the item if it matched, or nothing.

If `maybe_placeholders=False` (the default), then `[]` behaves like `()?`.

If `maybe_placeholders=True`, then using `[item]` will return the item if it matched, or the value `None`, if it didn't.

## Terminals

Terminals are always values in the tree, never branches.

Lark filters out certain types of terminals by default, considering them punctuation:

- Terminals that won't appear in the tree are:

    - Unnamed literals (like `"keyword"` or `"+"`)
    - Terminals whose name starts with an underscore (like `_DIGIT`)

- Terminals that *will* appear in the tree are:

    - Unnamed regular expressions (like `/[0-9]/`)
    - Named terminals whose name starts with a letter (like `DIGIT`)

Note: Terminals composed of literals and other terminals always include the entire match without filtering any part.

**Example:**
```
start:  PNAME pname

PNAME:  "(" NAME ")"
pname:  "(" NAME ")"

NAME:   /\w+/
%ignore /\s+/
```
Lark will parse "(Hello) (World)" as:

    start
        (Hello)
        pname World

Rules prefixed with `!` will retain all their literals regardless.




**Example:**

```perl
    expr: "(" expr ")"
        | NAME+

    NAME: /\w+/

    %ignore " "
```

Lark will parse "((hello world))" as:

    expr
        expr
            expr
                "hello"
                "world"

The brackets do not appear in the tree by design. The words appear because they are matched by a named terminal.


## Shaping the tree

Users can alter the automatic construction of the tree using a collection of grammar features.


* Rules whose name begins with an underscore will be inlined into their containing rule.

**Example:**

```perl
    start: "(" _greet ")"
    _greet: /\w+/ /\w+/
```

Lark will parse "(hello world)" as:

    start
        "hello"
        "world"


* Rules that receive a question mark (?) at the beginning of their definition, will be inlined if they have a single child, after filtering.

**Example:**

```ruby
    start: greet greet
    ?greet: "(" /\w+/ ")"
          | /\w+/ /\w+/
```

Lark will parse "hello world (planet)" as:

    start
        greet
            "hello"
            "world"
        "planet"

* Rules that begin with an exclamation mark will keep all their terminals (they won't get filtered).

```perl
    !expr: "(" expr ")"
         | NAME+
    NAME: /\w+/
    %ignore " "
```

Will parse "((hello world))" as:

    expr
      (
      expr
        (
        expr
          hello
          world
        )
      )

Using the `!` prefix is usually a "code smell", and may point to a flaw in your grammar design.

* Aliases - options in a rule can receive an alias. It will be then used as the branch name for the option, instead of the rule name.

**Example:**

```ruby
    start: greet greet
    greet: "hello"
         | "world" -> planet
```

Lark will parse "hello world" as:

    start
        greet
        planet
