"Transformer for evaluating csv.lark"

from lark import Transformer

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
