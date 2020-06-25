#
# This example demonstrates error handling using a parsing puppet in LALR
#
# When the parser encounters an UnexpectedToken exception, it creates a
# parsing puppet with the current parse-state, and lets you control how
# to proceed step-by-step. When you've achieved the correct parse-state,
# you can resume the run by returning True.
#

from lark import UnexpectedToken, Token

from .json_parser import json_parser

def ignore_errors(e):
    if e.token.type == 'COMMA':
        # Skip comma
        return True
    elif e.token.type == 'SIGNED_NUMBER':
        # Try to feed a comma and retry the number
        e.puppet.feed_token(Token('COMMA', ','))
        e.puppet.feed_token(e.token)
        return True

    # Unhandled error. Will stop parse and raise exception
    return False


def main():
    s = "[0 1, 2,, 3,,, 4, 5 6 ]"
    res = json_parser.parse(s, on_error=ignore_errors)
    print(res)      # prints [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0]

main()

