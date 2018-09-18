#
# This demonstrates example-driven error reporting with the LALR parser
#
# To run this, use:
#     python -m examples.error_reporting_lalr &> test.txt
#
import sys

from lark import Lark, LarkError, SyntaxErrors, UnexpectedInput
from lark.logging import getLogger

# Using the grammar from the json_parser example
from .json_parser import json_grammar

log = getLogger(__name__, 1)
json_parser = Lark(json_grammar, parser='lalr', debug=0)

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
        log(2, "error_reportings: %s", json_parser.parser.parser.parser.error_recovering)
        json_parser.parser.parser.parser.error_recovering = False

        candidates = []
        new_exceptions = []

        for label, example in examples.items():

            for malformed in example:
                try:
                    json_parser.parse(malformed)

                except LarkError as candidate:
                    candidates.append((candidate, label))

        log(2, "error_reportings: %s", json_parser.parser.parser.parser.error_recovering)
        log(2, "errors.exceptions(%s): %s", len(errors.exceptions), errors.exceptions)
        json_parser.parser.parser.parser.error_recovering = True

        for exception in errors.exceptions:
            exc_class = None

            """ Given a parser instance and a dictionary mapping some label with
                some malformed syntax examples, it'll return the label for the
                example that bests matches the current error.
            """
            # Try exact match first
            for candidate, label in candidates:
                assert exception.state is not None, "Not supported for this exception"

                if candidate.state == exception.state:
                    try:
                        if candidate.token == exception.token:
                            log(2, "Exactly match: %s", label)
                            exc_class = label
                    except AttributeError as error:
                        log(2, 'Could not get the token: %s', error)

            if not exc_class:
                for candidate, label in candidates:

                    if candidate.state == exception.state:
                        log(2, "Not exactly match: %s", label)
                        exc_class = label
                        break

            if not exc_class or exc_class not in examples.keys():
                new_exceptions.append(exception)
            else:
                new_exceptions.append(exc_class(exception.get_context(json_text), exception.line, exception.column))

        raise SyntaxErrors(new_exceptions)


def test():
    sys.stderr.write("\nParsing example 1\n")
    try:
        parse('{"example1": "value"')
    except SyntaxErrors as errors:
        sys.stderr.write("Caught %s exceptions:\n" % len(errors.exceptions))
        for exception in errors.exceptions:
            sys.stderr.write("%s\n" % exception)

    sys.stderr.write("\nParsing example 2\n")
    try:
        parse('{"example2": ] ')
    except SyntaxErrors as errors:
        sys.stderr.write("Caught %s exceptions:\n" % len(errors.exceptions))
        for exception in errors.exceptions:
            sys.stderr.write("%s\n" % exception)


if __name__ == '__main__':
    test()


