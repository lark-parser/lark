# Grammar Reference

Table of contents:

1. [Definitions](#defs)
1. [Terminals](#terms)
1. [Rules](#rules)
1. [Directives](#dirs)

<a name="defs"></a>
## Definitions

A **grammar** is a list of rules and terminals, that together define a language.

Terminals define the alphabet of the language, while rules define its structure.

In Lark, a terminal may be a string, a regular expression, or a concatenation of these and other terminals.

Each rule is a list of terminals and rules, whose location and nesting define the structure of the resulting parse-tree.

A **parsing algorithm** is an algorithm that takes a grammar definition and a sequence of symbols (members of the alphabet), and matches the entirety of the sequence by searching for a structure that is allowed by the grammar.

## General Syntax and notes

Grammars in Lark are based on [EBNF](https://en.wikipedia.org/wiki/Extended_Backus–Naur_form) syntax, with several enhancements.

EBNF is basically a short-hand for common BNF patterns.

Optionals are expanded:

```ebnf
  a b? c    ->    (a c | a b c)
```

Repetition is extracted into a recursion:

```ebnf
  a: b*    ->    a: _b_tag
                 _b_tag: (_b_tag b)?
```

And so on.

Lark grammars are composed of a list of definitions and directives, each on its own line. A definition is either a named rule, or a named terminal, with the following syntax, respectively:

```c
  rule: <EBNF EXPRESSION>
      | etc.

  TERM: <EBNF EXPRESSION>   // Rules aren't allowed
```


**Comments** start with `//` and last to the end of the line (C++ style)

Lark begins the parse with the rule 'start', unless specified otherwise in the options.

Names of rules are always in lowercase, while names of terminals are always in uppercase. This distinction has practical effects, for the shape of the generated parse-tree, and the automatic construction of the lexer (aka tokenizer, or scanner).


<a name="terms"></a>
## Terminals

Terminals are used to match text into symbols. They can be defined as a combination of literals and other terminals.

**Syntax:**

```html
<NAME> [. <priority>] : <literals-and-or-terminals>
```

Terminal names must be uppercase.

Literals can be one of:

* `"string"`
* `/regular expression+/`
* `"case-insensitive string"i`
* `/re with flags/imulx`
* Literal range: `"a".."z"`, `"1".."9"`, etc.

Terminals also support grammar operators, such as `|`, `+`, `*` and `?`.

Terminals are a linear construct, and therefore may not contain themselves (recursion isn't allowed).

### Priority

Terminals can be assigned priority only when using a lexer (future versions may support Earley's dynamic lexing).

Priority can be either positive or negative. If not specified for a terminal, it defaults to 1.

#### Notes for when using a lexer:

When using a lexer (standard or contextual), it is the grammar-author's responsibility to make sure the literals don't collide, or that if they do, they are matched in the desired order. Literals are matched according to the following precedence:

1. Highest priority first (priority is specified as: TERM.number: ...)
2. Length of match (for regexps, the longest theoretical match is used)
3. Length of literal / pattern definition
4. Name

**Examples:**
```perl
IF: "if"
INTEGER : /[0-9]+/
INTEGER2 : ("0".."9")+          //# Same as INTEGER
DECIMAL.2: INTEGER? "." INTEGER  //# Will be matched before INTEGER
WHITESPACE: (" " | /\t/ )+
SQL_SELECT: "select"i
```

### Regular expressions & Ambiguity

Each terminal is eventually compiled to a regular expression. All the operators and references inside it are mapped to their respective expressions.

For example, in the following grammar, `A1` and `A2`, are equivalent:
```perl
A1: "a" | "b"
A2: /a|b/
```

This means that inside terminals, Lark cannot detect or resolve ambiguity, even when using Earley.

For example, for this grammar:
```perl
start           : (A | B)+
A               : "a" | "ab"
B               : "b"
```
We get this behavior:

```bash
>>> p.parse("ab")
Tree(start, [Token(A, 'a'), Token(B, 'b')])
```

This is happening because Python's regex engine always returns the first matching option.

If you find yourself in this situation, the recommended solution is to use rules instead.

Example:

```python
>>> p = Lark("""start: (a | b)+
...             !a: "a" | "ab"
...             !b: "b"
...             """, ambiguity="explicit")
>>> print(p.parse("ab").pretty())
_ambig
  start
    a   ab
  start
    a   a
    b   b
```


<a name="rules"></a>
## Rules

**Syntax:**
```html
<name> : <items-to-match>  [-> <alias> ]
       | ...
```

Names of rules and aliases are always in lowercase.

Rule definitions can be extended to the next line by using the OR operator (signified by a pipe: `|` ).

An alias is a name for the specific rule alternative. It affects tree construction.


Each item is one of:

* `rule`
* `TERMINAL`
* `"string literal"` or `/regexp literal/`
* `(item item ..)` - Group items
* `[item item ..]` - Maybe. Same as `(item item ..)?`, but generates `None` if there is no match
* `item?` - Zero or one instances of item ("maybe")
* `item*` - Zero or more instances of item
* `item+` - One or more instances of item
* `item ~ n` - Exactly *n* instances of item
* `item ~ n..m` - Between *n* to *m* instances of item (not recommended for wide ranges, due to performance issues)

**Examples:**
```perl
hello_world: "hello" "world"
mul: (mul "*")? number     //# Left-recursion is allowed and encouraged!
expr: expr operator expr
    | value               //# Multi-line, belongs to expr

four_words: word ~ 4
```

### Priority

Rules can be assigned priority only when using Earley (future versions may support LALR as well).

Priority can be either positive or negative. In not specified for a terminal, it's assumed to be 1 (i.e. the default).

<a name="dirs"></a>
## Directives

### %ignore

All occurrences of the terminal will be ignored, and won't be part of the parse.

Using the `%ignore` directive results in a cleaner grammar.

It's especially important for the LALR(1) algorithm, because adding whitespace (or comments, or other extraneous elements) explicitly in the grammar, harms its predictive abilities, which are based on a lookahead of 1.

**Syntax:**
```html
%ignore <TERMINAL>
```
**Examples:**
```perl
%ignore " "

COMMENT: "#" /[^\n]/*
%ignore COMMENT
```
### %import

Allows to import terminals and rules from lark grammars.

When importing rules, all their dependencies will be imported into a namespace, to avoid collisions. It's not possible to override their dependencies (e.g. like you would when inheriting a class).

**Syntax:**
```html
%import <module>.<TERMINAL>
%import <module>.<rule>
%import <module>.<TERMINAL> -> <NEWTERMINAL>
%import <module>.<rule> -> <newrule>
%import <module> (<TERM1>, <TERM2>, <rule1>, <rule2>)
```

If the module path is absolute, Lark will attempt to load it from the built-in directory (currently, only `common.lark` is available).

If the module path is relative, such as `.path.to.file`, Lark will attempt to load it from the current working directory. Grammars must have the `.lark` extension.

The rule or terminal can be imported under an other name with the `->` syntax.

**Example:**
```perl
%import common.NUMBER

%import .terminals_file (A, B, C)

%import .rules_file.rulea -> ruleb
```

Note that `%ignore` directives cannot be imported. Imported rules will abide by the `%ignore` directives declared in the main grammar.

### %declare

Declare a terminal without defining it. Useful for plugins.
