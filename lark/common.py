
class GrammarError(Exception):
    pass

class ParseError(Exception):
    pass


def is_terminal(sym):
    return sym.isupper() or sym[0] == '$'

