"""
Grammar Composition
===================

This example shows how to do grammar composition in Lark, by creating a new
file format that allows both CSV and JSON to co-exist.

1) We define ``storage.lark``, which imports both ``csv.lark`` and ``json.lark``,
  and allows them to be used one after the other.

  In the generated tree, each imported rule/terminal is automatically prefixed (with ``json__`` or ``csv__),
  which creates an implicit namespace and allows them to coexist without collisions.

2) We merge their respective transformers (unaware of each other) into a new base transformer.
   The resulting transformer can evaluate both JSON and CSV in the parse tree.

  The methods of each transformer are renamed into their appropriate namespace, using the given prefix.
  This approach allows full re-use: the transformers don't need to care if their grammar is used directly,
  or being imported, or who is doing the importing.

"""
from pathlib import Path
from lark import Lark
from json import dumps
from lark.visitors import Transformer, merge_transformers

from eval_csv import CsvTreeToPandasDict
from eval_json import JsonTreeToJson

__dir__ = Path(__file__).parent

class Storage(Transformer):
    def start(self, children):
        return children

storage_transformer = merge_transformers(Storage(), csv=CsvTreeToPandasDict(), json=JsonTreeToJson())

parser = Lark.open("storage.lark", rel_to=__file__)

def main():
    json_tree = parser.parse(dumps({"test": "a", "dict": { "list": [1, 1.2] }}))
    res = storage_transformer.transform(json_tree)
    print("Just JSON: ", res)

    csv_json_tree = parser.parse(open(__dir__ / 'combined_csv_and_json.txt').read())
    res = storage_transformer.transform(csv_json_tree)
    print("JSON + CSV: ", dumps(res, indent=2))


if __name__ == "__main__":
    main()
