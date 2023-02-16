"""
Reconstruct Python
==================

Demonstrates how Lark's experimental text-reconstruction feature can recreate
functional Python code from its parse-tree, using just the correct grammar and
a small formatter.

"""

from lark import Token, Lark
from lark.reconstruct import Reconstructor
from lark.indenter import PythonIndenter

# Official Python grammar by Lark
python_parser3 = Lark.open_from_package('lark', 'python.lark', ['grammars'],
                                        parser='lalr', postlex=PythonIndenter(), start='file_input',
                                        maybe_placeholders=False    # Necessary for reconstructor
                                        )

SPACE_AFTER = set(',+-*/~@<>="|:')
SPACE_BEFORE = (SPACE_AFTER - set(',:')) | set('\'')


def special(sym):
    return Token('SPECIAL', sym.name)

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


class PythonReconstructor:
    def __init__(self, parser):
        self._recons = Reconstructor(parser, {'_NEWLINE': special, '_DEDENT': special, '_INDENT': special})

    def reconstruct(self, tree):
        return self._recons.reconstruct(tree, postproc)


def test():
    python_reconstructor = PythonReconstructor(python_parser3)

    self_contents = open(__file__).read()

    tree = python_parser3.parse(self_contents+'\n')
    output = python_reconstructor.reconstruct(tree)

    tree_new = python_parser3.parse(output)
    print(tree.pretty())
    print(tree_new.pretty())
    # assert tree.pretty() == tree_new.pretty()
    assert tree == tree_new

    print(output)


if __name__ == '__main__':
    test()
