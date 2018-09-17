#
# This demonstrates example-driven error reporting with the LALR parser
#

from lark import Lark, UnexpectedInput

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
    except UnexpectedInput as u:
    # except SyntaxErrors as errors:
    #     json_parser.parser.error_reporting = True
    #     candidates = []

    #     for label, example in examples.items():
    #         assert not isinstance(example, STRING_TYPE)

    #         for malformed in example:
    #             try:
    #                 json_parser.parse(malformed)

    #             except LarkError as ut:
    #                 candidates.append(candidates)

    #     for exception in errors.exceptions:

        exc_class = u.match_examples(json_parser.parse, {
            JsonMissingOpening: ['{"foo": ]}',
                                 '{"foor": }}',
                                 '{"foo": }'],
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
        raise exc_class(u.get_context(json_text), u.line, u.column)


def test():
    try:
        parse('{"example1": "value"')
    except JsonMissingClosing as e:
        print(e)

    try:
        parse('{"example2": ] ')
    except JsonMissingOpening as e:
        print(e)


if __name__ == '__main__':
    test()


