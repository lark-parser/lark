from lark import Lark, Tree
from json import dumps
from lark.visitors import Transformer, merge_transformers, v_args

class JsonTreeToJson(Transformer):
    @v_args(inline=True)
    def string(self, s):
        return s[1:-1].replace('\\"', '"')

    array = list
    pair = tuple
    object = dict
    number = v_args(inline=True)(float)

    null = lambda self, _: None
    true = lambda self, _: True
    false = lambda self, _: False

class CsvTreeToPandasDict(Transformer):
    INT = int
    FLOAT = float
    SIGNED_FLOAT = float
    WORD = str
    NON_SEPARATOR_STRING = str

    def row(self, children):
        return children

    def start(self, children):
        data = {}

        header = children[0].children
        for heading in header:
            data[heading] = []

        for row in children[1:]:
            for i, element in enumerate(row):
                data[header[i]].append(element)

        return data

class Base(Transformer):
    def start(self, children):
        return children[0]

if __name__ == "__main__":
    merged = merge_transformers(Base(), csv=CsvTreeToPandasDict(), json=JsonTreeToJson())
    parser = Lark.open("storage.lark")
    csv_tree = parser.parse("""# file lines author
data.json 12 Robin
data.csv  30 erezsh
compiler.py 123123 Megalng
""")
    print("CSV data in pandas form:", merged.transform(csv_tree))
    json_tree = parser.parse(dumps({"test": "a", "dict": { "list": [1, 1.2] }}))
    print("JSON data transformed: ", merged.transform(json_tree))
