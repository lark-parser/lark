# How To Use Lark - Guide

## Work process

This is the recommended process for working with Lark:

1. Collect or create input samples, that demonstrate key features or behaviors in the language you're trying to parse.

2. Write a grammar. Try to aim for a structure that is intuitive, and in a way that imitates how you would explain your language to a fellow human.

3. Try your grammar in Lark against each input sample. Make sure the resulting parse-trees make sense.

4. Use Lark's grammar features to [[shape the tree|Tree Construction]]: Get rid of superfluous rules by inlining them, and use aliases when specific cases need clarification. 

  - You can perform steps 1-4 repeatedly, gradually growing your grammar to include more sentences.

5. Create a transformer to evaluate the parse-tree into a structure you'll be comfortable to work with. This may include evaluating literals, merging branches, or even converting the entire tree into your own set of AST classes.

Of course, some specific use-cases may deviate from this process. Feel free to suggest these cases, and I'll add them to this page.

## Basic API Usage

For common use, you only need to know 3 classes: Lark, Tree, Transformer  ([[Classes Reference]])

Here is some mock usage of them. You can see a real example in the [[examples]]

```python
from lark import Lark, Transformer

grammar = """start: rules and more rules

             rule1: other rules AND TOKENS
                  | rule1 "+" rule2             -> add
                  | some value [maybe]
              
              rule2: rule1 "-" (rule2 | "whatever")*

              TOKEN1: "a literal"
              TOKEN2: TOKEN1 "and literals"
              """

parser = Lark(grammar)

tree = parser.parse("some input string")

class MyTransformer(Transformer):
   def rule1(self, matches):
      return matches[0] + matches[1]

   # I don't have to implement rule2 if I don't feel like it!

new_tree = MyTransformer().transform(tree)
```

