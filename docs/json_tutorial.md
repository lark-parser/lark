# JSON parser - Tutorial

Lark is a parser - a program that accepts a grammar and text, and produces a structured tree that represents that text.
In this tutorial we will write a JSON parser in Lark, and explore Lark's various features in the process.

It has 5 parts.

  1. Writing the grammar
  2. Creating the parser
  3. Shaping the tree
  4. Evaluating the tree
  5. Optimizing

Knowledge assumed:
- Using Python
- A basic understanding of how to use regular expressions

## Part 1 - The Grammar

Lark accepts its grammars in a format called [EBNF](https://www.wikiwand.com/en/Extended_Backus%E2%80%93Naur_form). It basically looks like this:

    rule_name : list of rules and TERMINALS to match
              | another possible list of items
              | etc.

    TERMINAL: "some text to match"

(*a terminal is a string or a regular expression*)

The parser will try to match each rule (left-part) by matching its items (right-part) sequentially, trying each alternative (In practice, the parser is predictive so we don't have to try every alternative).

How to structure those rules is beyond the scope of this tutorial, but often it's enough to follow one's intuition.

In the case of JSON, the structure is simple: A json document is either a list, or a dictionary, or a string/number/etc.

The dictionaries and lists are recursive, and contain other json documents (or "values").

Let's write this structure in EBNF form:

    value: dict
         | list
         | STRING
         | NUMBER
         | "true" | "false" | "null"

    list : "[" [value ("," value)*] "]"

    dict : "{" [pair ("," pair)*] "}"
    pair : STRING ":" value


A quick explanation of the syntax:
 - Parenthesis let us group rules together.
 - rule\* means *any amount*. That means, zero or more instances of that rule.
 - [rule] means *optional*. That means zero or one instance of that rule.

Lark also supports the rule+ operator, meaning one or more instances. It also supports the rule? operator which is another way to say *optional*.

Of course, we still haven't defined "STRING" and "NUMBER". Luckily, both these literals are already defined in Lark's common library:

    %import common.ESCAPED_STRING   -> STRING
    %import common.SIGNED_NUMBER    -> NUMBER

The arrow (->) renames the terminals. But that only adds obscurity in this case, so going forward we'll just use their original names.

We'll also take care of the white-space, which is part of the text.

    %import common.WS
    %ignore WS

We tell our parser to ignore whitespace. Otherwise, we'd have to fill our grammar with WS terminals.

By the way, if you're curious what these terminals signify, they are roughly equivalent to this:

    NUMBER : /-?\d+(\.\d+)?([eE][+-]?\d+)?/
    STRING : /".*?(?<!\\)"/
    %ignore /[ \t\n\f\r]+/

Lark will accept this, if you really want to complicate your life :)

You can find the original definitions in [common.lark](https://github.com/lark-parser/lark/blob/master/lark/grammars/common.lark).
They don't strictly adhere to [json.org](https://json.org/) - but our purpose here is to accept json, not validate it.

Notice that terminals are written in UPPER-CASE, while rules are written in lower-case.
I'll touch more on the differences between rules and terminals later.

## Part 2 - Creating the Parser

Once we have our grammar, creating the parser is very simple.

We simply instantiate Lark, and tell it to accept a "value":

```python
from lark import Lark
json_parser = Lark(r"""
    value: dict
         | list
         | ESCAPED_STRING
         | SIGNED_NUMBER
         | "true" | "false" | "null"

    list : "[" [value ("," value)*] "]"

    dict : "{" [pair ("," pair)*] "}"
    pair : ESCAPED_STRING ":" value

    %import common.ESCAPED_STRING
    %import common.SIGNED_NUMBER
    %import common.WS
    %ignore WS

    """, start='value')
```

It's that simple! Let's test it out:

```python
>>> text = '{"key": ["item0", "item1", 3.14]}'
>>> json_parser.parse(text)
Tree(value, [Tree(dict, [Tree(pair, [Token(STRING, "key"), Tree(value, [Tree(list, [Tree(value, [Token(STRING, "item0")]), Tree(value, [Token(STRING, "item1")]), Tree(value, [Token(NUMBER, 3.14)])])])])])])
>>> print( _.pretty() )
value
  dict
    pair
      "key"
      value
        list
          value	"item0"
          value	"item1"
          value	3.14
```

As promised, Lark automagically creates a tree that represents the parsed text.

But something is suspiciously missing from the tree. Where are the curly braces, the commas and all the other punctuation literals?

Lark automatically filters out literals from the tree, based on the following criteria:

- Filter out string literals without a name, or with a name that starts with an underscore.
- Keep regexps, even unnamed ones, unless their name starts with an underscore.

Unfortunately, this means that it will also filter out literals like "true" and "false", and we will lose that information. The next section, "Shaping the tree" deals with this issue, and others.

## Part 3 - Shaping the Tree

We now have a parser that can create a parse tree (or: AST), but the tree has some issues:

1. "true", "false" and "null" are filtered out (test it out yourself!)
2. Is has useless branches, like *value*, that clutter-up our view.

I'll present the solution, and then explain it:

    ?value: dict
          | list
          | string
          | SIGNED_NUMBER      -> number
          | "true"             -> true
          | "false"            -> false
          | "null"             -> null

    ...

    string : ESCAPED_STRING

1. Those little arrows signify *aliases*. An alias is a name for a specific part of the rule. In this case, we will name the *true/false/null* matches, and this way we won't lose the information. We also alias *SIGNED_NUMBER* to mark it for later processing.

2. The question-mark prefixing *value* ("?value") tells the tree-builder to inline this branch if it has only one member. In this case, *value* will always have only one member, and will always be inlined.

3. We turned the *ESCAPED_STRING* terminal into a rule. This way it will appear in the tree as a branch. This is equivalent to aliasing (like we did for the number), but now *string* can also be used elsewhere in the grammar (namely, in the *pair* rule).

Here is the new grammar:

```python
from lark import Lark
json_parser = Lark(r"""
    ?value: dict
          | list
          | string
          | SIGNED_NUMBER      -> number
          | "true"             -> true
          | "false"            -> false
          | "null"             -> null

    list : "[" [value ("," value)*] "]"

    dict : "{" [pair ("," pair)*] "}"
    pair : string ":" value

    string : ESCAPED_STRING

    %import common.ESCAPED_STRING
    %import common.SIGNED_NUMBER
    %import common.WS
    %ignore WS

    """, start='value')
```

And let's test it out:

```python
>>> text = '{"key": ["item0", "item1", 3.14, true]}'
>>> print( json_parser.parse(text).pretty() )
dict
  pair
    string	"key"
    list
      string	"item0"
      string	"item1"
      number	3.14
      true
```

Ah! That is much much nicer.

## Part 4 - Evaluating the tree

It's nice to have a tree, but what we really want is a JSON object.

The way to do it is to evaluate the tree, using a Transformer.

A transformer is a class with methods corresponding to branch names. For each branch, the appropriate method will be called with the children of the branch as its argument, and its return value will replace the branch in the tree.

So let's write a partial transformer, that handles lists and dictionaries:

```python
from lark import Transformer

class MyTransformer(Transformer):
    def list(self, items):
        return list(items)
    def pair(self, key_value):
        k, v = key_value
        return k, v
    def dict(self, items):
        return dict(items)
```

And when we run it, we get this:
```python
>>> tree = json_parser.parse(text)
>>> MyTransformer().transform(tree)
{Tree(string, [Token(ANONRE_1, "key")]): [Tree(string, [Token(ANONRE_1, "item0")]), Tree(string, [Token(ANONRE_1, "item1")]), Tree(number, [Token(ANONRE_0, 3.14)]), Tree(true, [])]}
```

This is pretty close. Let's write a full transformer that can handle the terminals too.

Also, our definitions of list and dict are a bit verbose. We can do better:

```python
from lark import Transformer

class TreeToJson(Transformer):
    def string(self, s):
        (s,) = s
        return s[1:-1]
    def number(self, n):
        (n,) = n
        return float(n)

    list = list
    pair = tuple
    dict = dict

    null = lambda self, _: None
    true = lambda self, _: True
    false = lambda self, _: False
```

And when we run it:

```python
>>> tree = json_parser.parse(text)
>>> TreeToJson().transform(tree)
{u'key': [u'item0', u'item1', 3.14, True]}
```
Magic!

## Part 5 - Optimizing

### Step 1 - Benchmark

By now, we have a fully working JSON parser, that can accept a string of JSON, and return its Pythonic representation.

But how fast is it?

Now, of course there are JSON libraries for Python written in C, and we can never compete with them. But since this is applicable to any parser you would write in Lark, let's see how far we can take this.

The first step for optimizing is to have a benchmark. For this benchmark I'm going to take data from [json-generator.com/](http://www.json-generator.com/). I took their default suggestion and changed it to 5000 objects. The result is a 6.6MB sparse JSON file.

Our first program is going to be just a concatenation of everything we've done so far:

```python
import sys
from lark import Lark, Transformer

json_grammar = r"""
    ?value: dict
          | list
          | string
          | SIGNED_NUMBER      -> number
          | "true"             -> true
          | "false"            -> false
          | "null"             -> null

    list : "[" [value ("," value)*] "]"

    dict : "{" [pair ("," pair)*] "}"
    pair : string ":" value

    string : ESCAPED_STRING

    %import common.ESCAPED_STRING
    %import common.SIGNED_NUMBER
    %import common.WS
    %ignore WS
    """

class TreeToJson(Transformer):
    def string(self, s):
        (s,) = s
        return s[1:-1]
    def number(self, n):
        (n,) = n
        return float(n)

    list = list
    pair = tuple
    dict = dict

    null = lambda self, _: None
    true = lambda self, _: True
    false = lambda self, _: False

json_parser = Lark(json_grammar, start='value', lexer='standard')

if __name__ == '__main__':
    with open(sys.argv[1]) as f:
        tree = json_parser.parse(f.read())
        print(TreeToJson().transform(tree))
```

We run it and get this:

    $ time python tutorial_json.py json_data > /dev/null

    real	0m36.257s
    user	0m34.735s
    sys         0m1.361s


That's unsatisfactory time for a 6MB file. Maybe if we were parsing configuration or a small DSL, but we're trying to handle large amount of data here.

Well, turns out there's quite a bit we can do about it!

### Step 2 - LALR(1)

So far we've been using the Earley algorithm, which is the default in Lark. Earley is powerful but slow. But it just so happens that our grammar is LR-compatible, and specifically LALR(1) compatible.

So let's switch to LALR(1) and see what happens:

```python
json_parser = Lark(json_grammar, start='value', parser='lalr')
```
    $ time python tutorial_json.py json_data > /dev/null

    real        0m7.554s
    user        0m7.352s
    sys         0m0.148s

Ah, that's much better. The resulting JSON is of course exactly the same. You can run it for yourself and see.

It's important to note that not all grammars are LR-compatible, and so you can't always switch to LALR(1). But there's no harm in trying! If Lark lets you build the grammar, it means you're good to go.

### Step 3 - Tree-less LALR(1)

So far, we've built a full parse tree for our JSON, and then transformed it. It's a convenient method, but it's not the most efficient in terms of speed and memory. Luckily, Lark lets us avoid building the tree when parsing with LALR(1).

Here's the way to do it:

```python
json_parser = Lark(json_grammar, start='value', parser='lalr', transformer=TreeToJson())

if __name__ == '__main__':
    with open(sys.argv[1]) as f:
        print( json_parser.parse(f.read()) )
```

We've used the transformer we've already written, but this time we plug it straight into the parser. Now it can avoid building the parse tree, and just send the data straight into our transformer. The *parse()* method now returns the transformed JSON, instead of a tree.

Let's benchmark it:

    real	0m4.866s
    user	0m4.722s
    sys 	0m0.121s

That's a measurable improvement! Also, this way is more memory efficient. Check out the benchmark table at the end to see just how much.

As a general practice, it's recommended to work with parse trees, and only skip the tree-builder when your transformer is already working.

### Step 4 - PyPy

PyPy is a JIT engine for running Python, and it's designed to be a drop-in replacement.

Lark is written purely in Python, which makes it very suitable for PyPy.

Let's get some free performance:

    $ time pypy tutorial_json.py json_data > /dev/null

    real	0m1.397s
    user	0m1.296s
    sys 	0m0.083s

PyPy is awesome!

### Conclusion

We've brought the run-time down from 36 seconds to 1.1 seconds, in a series of small and simple steps.

Now let's compare the benchmarks in a nicely organized table.

I measured memory consumption using a little script called [memusg](https://gist.github.com/netj/526585)

| Code | CPython Time | PyPy Time | CPython Mem | PyPy Mem
|:-----|:-------------|:------------|:----------|:---------
| Lark - Earley *(with lexer)* | 42s | 4s | 1167M | 608M |
| Lark - LALR(1) | 8s | 1.53s | 453M | 266M |
| Lark - LALR(1) tree-less | 4.76s | 1.23s | 70M | 134M |
| PyParsing ([Parser](http://pyparsing.wikispaces.com/file/view/jsonParser.py)) | 32s | 3.53s | 443M | 225M |
| funcparserlib ([Parser](https://github.com/vlasovskikh/funcparserlib/blob/master/funcparserlib/tests/json.py)) | 8.5s | 1.3s | 483M | 293M |
| Parsimonious ([Parser](https://gist.githubusercontent.com/reclosedev/5222560/raw/5e97cf7eb62c3a3671885ec170577285e891f7d5/parsimonious_json.py)) | ? | 5.7s | ? | 1545M |


I added a few other parsers for comparison. PyParsing and funcparselib fair pretty well in their memory usage (they don't build a tree), but they can't compete with the run-time speed of LALR(1).

These benchmarks are for Lark's alpha version. I already have several optimizations planned that will significantly improve run-time speed.

Once again, shout-out to PyPy for being so effective.

## Afterword

This is the end of the tutorial. I hoped you liked it and learned a little about Lark.

To see what else you can do with Lark, check out the [examples](examples).

For questions or any other subject, feel free to email me at erezshin at gmail dot com.

