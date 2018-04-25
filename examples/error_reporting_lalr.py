#
# This demonstrates example-driven error reporting with the LALR parser
#

from lark import Lark, UnexpectedToken

from .json_parser import json_grammar   # Using the grammar from the json_parser example

json_parser = Lark(json_grammar, parser='lalr')

class JsonSyntaxError(SyntaxError):
    def __str__(self):
        context, line, column = self.args
        return '%s at line %s, column %s.\n\n%s' % (self.label, line, column, context)

class JsonMissingValue(JsonSyntaxError):
    label = 'Missing Value'

class JsonMissingOpening(JsonSyntaxError):
    label = 'Missing Opening'

class JsonMissingClosing(JsonSyntaxError):
    label = 'Missing Closing'

class JsonMissingComma(JsonSyntaxError):
    label = 'Missing Comma'

class JsonTrailingComma(JsonSyntaxError):
    label = 'Trailing Comma'


def parse(json_text):
    try:
        j = json_parser.parse(json_text)
    except UnexpectedToken as ut:
        exc_class = ut.match_examples(json_parser.parse, {
            JsonMissingValue: ['{"foo": }'],
            JsonMissingOpening: ['{"foo": ]}',
                                 '{"foor": }}'],
            JsonMissingClosing: ['{"foo": [}',
                                 '{',
                                 '{"a": 1',
                                 '[1'],
            JsonMissingComma: ['[1 2]',
                               '[false 1]',
                               '["b" 1]',
                               '{"a":true 1:4}',
                               '{"a":1 1:4}',
                               '{"a":"b" 1:4}'],
            JsonTrailingComma: ['[,]',
                                '[1,]',
                                '[1,2,]',
                                '{"foo":1,}',
                                '{"foo":false,"bar":true,}']
        })
        if not exc_class:
            raise
        raise exc_class(ut.get_context(json_text), ut.line, ut.column)


def test():
    try:
        parse('{"key":')
    except JsonMissingValue:
        pass

    try:
        parse('{"key": "value"')
    except JsonMissingClosing:
        pass

    try:
        parse('{"key": ] ')
    except JsonMissingOpening:
        pass


if __name__ == '__main__':
    test()


