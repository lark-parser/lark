# Grammar Reference

## Definitions

**A grammar** is a list of rules and terminals, that together define a language.

Terminals define the alphabet of the language, while rules define its structure.

In Lark, a terminal may be a string, a regular expression, or a concatenation of these and other terminals.

Each rule is a list of terminals and rules, whose location and nesting define the structure of the resulting parse-tree.

A **parsing algorithm** is an algorithm that takes a grammar definition and a sequence of symbols (members of the alphabet), and matches the entirety of the sequence by searching for a structure that is allowed by the grammar.

## General Syntax and notes

Grammars in Lark are based on [EBNF](https://en.wikipedia.org/wiki/Extended_Backus–Naur_form) syntax, with several enhancements.

Lark grammars are composed of a list of definitions and directives, each on its own line. A definition is either a named rule, or a named terminal.

**Comments** start with `//` and last to the end of the line (C++ style)

Lark begins the parse with the rule 'start', unless specified otherwise in the options.

Names of rules are always in lowercase, while names of terminals are always in uppercase. This distinction has practical effects for tree construction, and for building a lexer (aka tokenizer, or scanner).


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
* Literal range: `"a".."z"`, `"1..9"`, etc.

#### Notes for when using a lexer:

When using a lexer (standard or contextual), it is the grammar-author's responsibility to make sure the literals don't collide, or that if they do, they are matched in the desired order. Literals are matched in an order according to the following criteria:

1. Highest priority first (priority is specified as: TERM.number: ...)
2. Length of match (for regexps, the longest theoretical match is used)
3. Length of literal / pattern definition
4. Name

**Examples:**
```perl
IF: "if"
INTEGER : /[0-9]+/
INTEGER2 : ("0".."9")+          //# Same as INTEGER
DECIMAL.2: INTEGER "." INTEGER  //# Will be matched before INTEGER
WHITESPACE: (" " | /\t/ )+
SQL_SELECT: "select"i
```

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
* `[item item ..]` - Maybe. Same as: `(item item ..)?`
* `item?` - Zero or one instances of item ("maybe")
* `item*` - Zero or more instances of item
* `item+` - One or more instances of item
* `item ~ n` - Exactly *n* instances of item
* `item ~ n..m` - Between *n* to *m* instances of item

**Examples:**
```perl
hello_world: "hello" "world"
mul: [mul "*"] number     //# Left-recursion is allowed!
expr: expr operator expr
    | value               //# Multi-line, belongs to expr

four_words: word ~ 4
```


## Directives

### %ignore

All occurrences of the terminal will be ignored, and won't be part of the parse.

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

Allows to import terminals from lark grammars.

Future versions will allow to import rules and macros.

**Syntax:**
```html
%import <module>.<TERMINAL>
%import <module> (<TERM1> <TERM2>)
```

If the module path is absolute, Lark will attempt to load it from the built-in directory (currently, only `common.lark` is available).

If the module path is relative, such as `.path.to.file`, Lark will attempt to load it from the current working directory. Grammars must have the `.lark` extension.

**Example:**
```perl
%import common.NUMBER

%import .terminals_file (A B C)
```

### %declare

Declare a terminal without defining it. Useful for plugins.