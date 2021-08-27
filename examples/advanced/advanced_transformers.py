from lark import Lark, Tree
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

    def start(self, children):
        data = {}

        header = children[0].children
        for heading in header:
            data[heading] = []

        for row in children[1:]:
            for i, element in enumerate(row):
                data[header[i]].append(element)

if __name__ == "__main__":
    merged = merge_transformers(csv=CsvTreeToPandasDict, json=JsonTreeToJson)
    print(dir(merged))
    parser = Lark.open("storage.lark")
    tree = parser.parse("""# file lines author
data.json 12 Robin
data.csv  30 erezsh
compiler.py 123123 Megalng
""")
    print("CSV data in pandas form:", merged.transform(tree))
