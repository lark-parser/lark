# Tools (Stand-alone, Nearley)

## Stand-alone parser

Lark can generate a stand-alone LALR(1) parser from a grammar.

The resulting module provides the same interface as Lark, but with a fixed grammar, and reduced functionality.

Run using:

```bash
python -m lark.tools.standalone
```

For a play-by-play, read the [tutorial](http://blog.erezsh.com/create-a-stand-alone-lalr1-parser-in-python/)

### Python API

Use `gen_standalone()` to generate a stand-alone parser from a `Lark` instance. This is useful when the grammar is stored in Python code instead of a separate grammar file.

```python
from io import StringIO

from lark import Lark
from lark.tools.standalone import gen_standalone

parser = Lark('start: WORD\n%import common.WORD', parser='lalr')
source = StringIO()
gen_standalone(parser, out=source)
standalone_source = source.getvalue()
```

The full signature is `gen_standalone(lark_inst, output=None, out=sys.stdout, compress=False)`. The function writes Python source to the text stream passed as `out` and returns `None`. Pass `out` and `compress` by keyword, because the second positional argument is the low-level `output` callback.

It accepts these arguments, in signature order:

- `lark_inst`: a `Lark` instance configured with the LALR parser.
- `output`: an advanced, print-compatible output callback. When provided, it takes precedence over `out`.
- `out`: the text stream that receives the generated source. It defaults to standard output.
- `compress`: if `True`, compress the serialized parser data embedded in the generated source.

Passing a `Lark` instance configured for another parser raises `NotImplementedError`.

To write the parser directly to a module:

```python
with open('standalone_parser.py', 'w', encoding='utf-8') as f:
    gen_standalone(parser, out=f, compress=True)
```

The generator and its generated code are licensed under the Mozilla Public License 2.0 (MPL-2.0), separately from Lark's main license.


## Importing grammars from Nearley.js

Lark comes with a tool to convert grammars from [Nearley](https://github.com/Hardmath123/nearley), a popular Earley library for Javascript. It uses [Js2Py](https://github.com/PiotrDabkowski/Js2Py) to convert and run the Javascript postprocessing code segments.

#### Requirements

1. Install Lark with the `nearley` component:
```bash
pip install lark[nearley]
```

2. Acquire a copy of the Nearley codebase. This can be done using:
```bash
git clone https://github.com/Hardmath123/nearley
```

#### Usage

The tool can be run using:

```bash
python -m lark.tools.nearley <grammar.ne> <start_rule> <path_to_nearley_repo>
```

Here's an example of how to import nearley's calculator example into Lark:

```bash
git clone https://github.com/Hardmath123/nearley
python -m lark.tools.nearley nearley/examples/calculator/arithmetic.ne main ./nearley > ncalc.py
```

You can use the output as a regular python module:

```python
>>> import ncalc
>>> ncalc.parse('sin(pi/4) ^ e')
0.38981434460254655
```

The Nearley converter also supports an experimental converter for newer JavaScript (ES6+), using the `--es6` flag:

```bash
git clone https://github.com/Hardmath123/nearley
python -m lark.tools.nearley nearley/examples/calculator/arithmetic.ne main nearley --es6 > ncalc.py
```

#### Notes

- Lark currently cannot import templates from Nearley

- Lark currently cannot export grammars to Nearley

These might get added in the future, if enough users ask for them.
