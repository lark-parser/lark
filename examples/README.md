# Examples for Lark

#### How to run the examples

After cloning the repo, open the terminal into the root directory of the project, and run the following:

```bash
[lark]$ python -m examples.<name_of_example>
```

For example, the following will parse all the Python files in the standard library of your local installation:

```bash
[lark]$ python -m examples.python_parser
```

### Beginners

- [calc.py](calc.py) - A simple example of a REPL calculator
- [json\_parser.py](json_parser.py) - A simple JSON parser (comes with a tutorial, see docs)
- [indented\_tree.py](indented\_tree.py) - A demonstration of parsing indentation ("whitespace significant" language)
- [fruitflies.py](fruitflies.py) - A demonstration of ambiguity
- [turtle\_dsl.py](turtle_dsl.py) - Implements a LOGO-like toy language for Python's turtle, with interpreter.
- [lark\_grammar.py](lark_grammar.py) + [lark.lark](lark.lark) - A reference implementation of the Lark grammar (using LALR(1) + standard lexer)

### Advanced

- [error\_reporting\_lalr.py](error_reporting_lalr.py) - A demonstration of example-driven error reporting with the LALR parser
- [python\_parser.py](python_parser.py) - A fully-working Python 2 & 3 parser (but not production ready yet!)
- [conf\_lalr.py](conf_lalr.py) - Demonstrates the power of LALR's contextual lexer on a toy configuration language
- [conf\_earley.py](conf_earley.py) - Demonstrates the power of Earley's dynamic lexer on a toy configuration language
- [custom\_lexer.py](custom_lexer.py) - Demonstrates using a custom lexer to parse a non-textual stream of data
- [reconstruct\_json.py](reconstruct_json.py) - Demonstrates the experimental text-reconstruction feature
