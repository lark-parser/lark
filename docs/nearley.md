# Importing grammars from Nearley

Lark comes with a tool to convert grammars from [Nearley](https://github.com/Hardmath123/nearley), a popular Earley library for Javascript. It uses [Js2Py](https://github.com/PiotrDabkowski/Js2Py) to convert and run the Javascript postprocessing code segments.

## Requirements

1. Install Lark with the `nearley` component:
```bash
pip install lark-parser[nearley]
```

2. Acquire a copy of the nearley codebase. This can be done using:
```bash
git clone https://github.com/Hardmath123/nearley
```

## Usage

Here's an example of how to import nearley's calculator example into Lark:

```bash
git clone https://github.com/Hardmath123/nearley
python -m lark.tools.nearley nearley/examples/calculator/arithmetic.ne main nearley > ncalc.py
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

## Notes

- Lark currently cannot import templates from Nearley

- Lark currently cannot export grammars to Nearley

These might get added in the future, if enough users ask for them.