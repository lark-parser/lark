#
# This demonstrates example-driven error reporting with the LALR parser
#

from lark import Lark, LarkError, SyntaxErrors, UnexpectedInput
from debug_tools import getLogger

from .json_parser import json_grammar   # Using the grammar from the json_parser example

log = getLogger(__name__)
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
    except SyntaxErrors as errors:
        examples = \
        {
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
        }
        json_parser.parser.error_reporting = True

        candidates = []
        new_exceptions = []

        for label, example in examples.items():

            for malformed in example:
                try:
                    json_parser.parse(malformed)

                except LarkError as candidate:
                    log(2, "Saving candidate %s %s", type(candidate), candidate)
                    candidates.append((candidate, label))

        for exception in errors.exceptions:

            for candidate, label in candidates:
                exc_class = exception.match_examples(candidate, label)
                if not exc_class or exc_class not in examples.keys():
                    raise
                else:
                    new_exceptions.append(exc_class(candidate.get_context(json_text), candidate.line, candidate.column))

        for new_exception in new_exceptions:
            print(new_exception)


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


