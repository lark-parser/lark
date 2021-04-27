# Philosophy

Parsers are innately complicated and confusing. They're difficult to understand, difficult to write, and difficult to use. Even experts on the subject can become baffled by the nuances of these complicated state-machines.

Lark's mission is to make the process of writing them as simple and abstract as possible, by following these design principles:

## Design Principles

1. Readability matters

2. Keep the grammar clean and simple

2. Don't force the user to decide on things that the parser can figure out on its own

4. Usability is more important than performance

5. Performance is still very important

6. Follow the Zen of Python, whenever possible and applicable


In accordance with these principles, I arrived at the following design choices:

-----------

## Design Choices

### 1. Separation of code and grammar

Grammars are the de-facto reference for your language, and for the structure of your parse-tree. For any non-trivial language, the conflation of code and grammar always turns out convoluted and difficult to read.

The grammars in Lark are EBNF-inspired, so they are especially easy to read & work with.

### 2. Always build a parse-tree (unless told not to)

Trees are always simpler to work with than state-machines.

1. Trees allow you to see the "state-machine" visually

2. Trees allow your computation to be aware of previous and future states

3. Trees allow you to process the parse in steps, instead of forcing you to do it all at once.

And anyway, every parse-tree can be replayed as a state-machine, so there is no loss of information.

See this answer in more detail [here](https://github.com/erezsh/lark/issues/4).

To improve performance, you can skip building the tree for LALR(1), by providing Lark with a transformer (see the [JSON example](https://github.com/erezsh/lark/blob/master/examples/json_parser.py)).

### 3. Earley is the default

The Earley algorithm can accept *any* context-free grammar you throw at it (i.e. any grammar you can write in EBNF, it can parse). That makes it extremely friendly to beginners, who are not aware of the strange and arbitrary restrictions that LALR(1) places on its grammars.

As the users grow to understand the structure of their grammar, the scope of their target language, and their performance requirements, they may choose to switch over to LALR(1) to gain a huge performance boost, possibly at the cost of some language features.

Both Earley and LALR(1) can use the same grammar, as long as all constraints are satisfied.

In short, "Premature optimization is the root of all evil."

### Other design features

- Automatically resolve terminal collisions whenever possible

- Automatically keep track of line & column numbers

