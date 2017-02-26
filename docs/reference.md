# Lark Reference

## What is Lark?

Lark is a general-purpose parsing library. It's written in Python, and supports two parsing algorithms: Earley (default) and LALR(1).

Lark also supports scanless parsing (with Earley), contextual lexing (with LALR), and regular lexing for both parsers.

Lark is a re-write of my previous parsing library, [PlyPlus](https://github.com/erezsh/plyplus).

## Grammar

Lark accepts its grammars in [EBNF](https://www.wikiwand.com/en/Extended_Backus%E2%80%93Naur_form) form.

The grammar is a list of rules and terminals, each in their own line.

Rules and terminals can be defined on multiple lines when using the *OR* operator ( | ).

Comments start with // and last to the end of the line (C++ style)

Lark begins the parse with the rule 'start', unless specified otherwise in the options.

It might help to think of Rules and Terminals as existing in two separate layers, so that all the terminals are recognized first, and all the rules are recognized afterwards. This is not always how things happen (depending on your choice of parser & lexer), but the concept is relevant in all cases.

### Rules

Each rule is defined in terms of:

    name : list of items to match
         | another list of items    -> optional_alias
         | etc.

An alias is a name for the specific rule alternative. It affects tree construction.

An item is a:

 - rule
 - terminal
 - (item item ..) - Group items
 - [item item ..] - Maybe. Same as: "(item item ..)?"
 - item? - Zero or one instances of item ("maybe")
 - item\* - Zero or more instances of item
 - item+ - One or more instances of item


Example:

    float: "-"? DIGIT* "." DIGIT+ exp
         | "-"? DIGIT+ exp

    exp: "-"? ("e" | "E") DIGIT+

    DIGIT: /[0-9]/

### Terminals

Terminals are defined just like rules, but cannot contain rules:

    NAME : list of items to match

Example:

    IF: "if"
    INTEGER : /[0-9]+/
    DECIMAL: INTEGER "." INTEGER
    WHITESPACE: (" " | /\t/ )+

## Tree Construction

Lark builds a tree automatically based on the structure of the grammar. Is also accepts some hints.

In general, Lark will place each rule as a branch, and its matches as the children of the branch.

Terminals are always values in the tree, never branches.

In grammar rules, using item+ or item\* will result in a list of items.

Example:

    expr: "(" expr ")"
        | NAME+

    NAME: /\w+/

    %ignore " "

Lark will parse "(((hello world)))" as:

    expr
        expr
            expr
                "hello"
                "world"

The brackets do not appear in the tree by design.

Terminals that won't appear in the tree are:

 - Unnamed literals (like "keyword" or "+")
 - Terminals whose name starts with an underscore (like \_DIGIT)

Terminals that *will* appear in the tree are:

 - Unnamed regular expressions (like /[0-9]/)
 - Named terminals whose name starts with a letter (like DIGIT)

## Shaping the tree

a. Rules whose name begins with an underscore will be inlined into their containing rule.

Example:

    start: "(" _greet ")"
    _greet: /\w+/ /\w+/

Lark will parse "(hello world)" as:

    start
        "hello"
        "world"


b. Rules that receive a question mark (?) at the beginning of their definition, will be inlined if they have a single child.

Example:

    start: greet greet
    ?greet: "(" /\w+/ ")"
          | /\w+ /\w+/

Lark will parse "hello world (planet)" as:

    start
        greet
            "hello"
            "world"
        "planet"

c. Rules that begin with an exclamation mark will keep all their terminals (they won't get filtered).

d. Aliases - options in a rule can receive an alias. It will be then used as the branch name for the option.

Example:

    start: greet greet
    greet: "hello" -> hello
         | "world"

Lark will parse "hello world" as:

    start
        hello
        greet

## Lark Options

When initializing the Lark object, you can provide it with keyword options:

- start - The start symbol (Default: "start")
- parser - Decides which parser engine to use, "earley" or "lalr". (Default: "earley")
           Note: "lalr" requires a lexer
- lexer - Decides whether or not to use a lexer stage
    - None: Don't use a lexer
    - "standard": Use a standard lexer
    - "contextual": Stronger lexer (only works with parser="lalr")
    - "auto" (default): Choose for me based on grammar and parser

- transformer - Applies the transformer to every parse tree (only allowed with parser="lalr")
- postlex - Lexer post-processing (Default: None)

To be supported:

- debug
- cache\_grammar
- keep\_all\_tokens
- profile - Measure run-time usage in Lark. Read results from the profiler property (Default: False)
