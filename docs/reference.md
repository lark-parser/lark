# Lark Reference

## What is Lark?

Lark is a general-purpose parsing library. It's written in Python, and supports two parsing algorithms: Earley (default) and LALR(1).

## Grammar

Lark accepts its grammars in [EBNF](https://www.wikiwand.com/en/Extended_Backus%E2%80%93Naur_form) form.

The grammar is a list of rules and tokens, each in their own line.

Rules can be defined on multiple lines when using the *OR* operator ( | ).

Comments start with // and last to the end of the line (C++ style)

Lark begins the parse with the rule 'start', unless specified otherwise in the options.

### Tokens

Tokens are defined in terms of:

    NAME : "string" or /regexp/
                   
    NAME.ignore : ..

.ignore is a flag that drops the token before it reaches the parser (usually whitespace)

Example:

    IF: "if"

    INTEGER : /[0-9]+/

    WHITESPACE.ignore: /[ \t\n]+/

### Rules

Each rule is defined in terms of:

    name : list of items to match
         | another list of items    -> optional_alias
         | etc.

An alias is a name for the specific rule alternative. It affects tree construction.

An item is a:
    
 - rule
 - token
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

## Tree Construction

Lark builds a tree automatically based on the structure of the grammar. Is also accepts some hints.

In general, Lark will place each rule as a branch, and its matches as the children of the branch.

Using item+ or item\* will result in a list of items.

Example:

    expr: "(" expr ")"
        | NAME+

    NAME: /\w+/

Lark will parse "(((hello world)))" as:

    expr
        expr
            expr
                "hello"
                "world"

The brackets do not appear in the tree by design.

Tokens that won't appear in the tree are:

 - Unnamed strings (like "keyword" or "+")
 - Tokens whose name starts with an underscore (like \_DIGIT)

Tokens that *will* appear in the tree are:

 - Unnamed regular expressions (like /[0-9]/)
 - Named tokens whose name starts with a letter (like DIGIT)

## Shaping the tree

a. Rules whose name begins with an underscore will be inlined into their containing rule.

Example:

    start: "(" _greet ")"
    _greet: /\w+/ /\w+/

Lark will parse "(hello world)" as:

    start
        "hello"
        "world"


b. Rules that recieve a question mark (?) at the beginning of their definition, will be inlined if they have a single child.

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

c. Aliases - options in a rule can receive an alias. It will be then used as the branch name for the option.

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
           Note: Both will use Lark's lexer.
- transformer - Applies the transformer to every parse tree (only allowed with parser="lalr")
- only\_lex - Don't build a parser. Useful for debugging (default: False)
- postlex - Lexer post-processing (Default: None)
- profile - Measure run-time usage in Lark. Read results from the profiler proprety (Default: False)  

To be supported:

- debug
- cache\_grammar
- keep\_all\_tokens

