
class Rule(object):
    """
        origin : a symbol
        expansion : a list of symbols
    """
    def __init__(self, origin, expansion, alias=None, options=None):
        self.origin = origin
        self.expansion = expansion
        self.alias = alias
        self.options = options

    def __repr__(self):
        return '<%s : %s>' % (self.origin, ' '.join(map(str,self.expansion)))


