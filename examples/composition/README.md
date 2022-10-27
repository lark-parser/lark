Grammar Composition
===================

This example shows how to do grammar composition in Lark, by creating a new
file format that allows both CSV and JSON to co-exist.

We show how, by using namespaces, Lark grammars and their transformers can be fully reused -
they don't need to care if their grammar is used directly, or being imported, or who is doing the importing.

See [``main.py``](main.py) for more details.
