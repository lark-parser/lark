from lark import Token
from lark.reconstruct import Reconstructor

from python_parser import python_parser3


test_python = open(__file__).read()

def special(sym):
    return Token('SPECIAL', sym.name)

SPACE_AFTER = set(',+-*/~@<>="|:')
SPACE_BEFORE = (SPACE_AFTER - set(',:')) | set('\'')

def postproc(items):
    stack = ['\n']
    actions = []
    last_was_whitespace = True
    for item in items:
        if isinstance(item, Token) and item.type == 'SPECIAL': 
            actions.append(item.value)
        else:
            if actions:
                assert actions[0] == '_NEWLINE' and '_NEWLINE' not in actions[1:], actions

                for a in actions[1:]:
                    if a == '_INDENT':
                        stack.append(stack[-1] + ' ' * 4)
                    else:
                        assert a == '_DEDENT'
                        stack.pop()
                actions.clear()
                yield stack[-1]
                last_was_whitespace = True
            if not last_was_whitespace:
                if item[0] in SPACE_BEFORE:
                    yield ' '
            yield item
            last_was_whitespace = item[-1].isspace()
            if not last_was_whitespace:
                if item[-1] in SPACE_AFTER:
                    yield ' '
                    last_was_whitespace = True
    yield "\n"


tree = python_parser3.parse(test_python)


python_reconstruct = Reconstructor(python_parser3, {'_NEWLINE': special, '_DEDENT': special, '_INDENT': special})

output = python_reconstruct.reconstruct(tree, postproc)

print(output)

tree_new = python_parser3.parse(output)

assert tree == tree_new
