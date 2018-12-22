class Symbol(object):
    is_term = NotImplemented

    def __init__(self, name):
        self.name = name

    def __eq__(self, other):
        assert isinstance(other, Symbol), other
        return self.is_term == other.is_term and self.name == other.name

    def __ne__(self, other):
        return not (self == other)

    def __hash__(self):
        return hash(self.name)

    def __repr__(self):
        return '%s(%r)' % (type(self).__name__, self.name)

    fullrepr = property(__repr__)

class Terminal(Symbol):
    is_term = True

    def __init__(self, name, filter_out=False):
        self.name = name
        self.filter_out = filter_out

    @property
    def fullrepr(self):
        return '%s(%r, %r)' % (type(self).__name__, self.name, self.filter_out)


class NonTerminal(Symbol):
    is_term = False

class Rule(object):
    """
        origin : a symbol
        expansion : a list of symbols
        order : index of this expansion amongst all rules of the same name
    """
    __slots__ = ('origin', 'expansion', 'alias', 'options', 'order', '_hash')
    def __init__(self, origin, expansion, order=0, alias=None, options=None):
        self.origin = origin
        self.expansion = expansion
        self.alias = alias
        self.order = order
        self.options = options
        self._hash = hash((self.origin, tuple(self.expansion)))


    def __str__(self):
        return '<%s : %s>' % (self.origin.name, ' '.join(x.name for x in self.expansion))

    def __repr__(self):
        return 'Rule(%r, %r, %r, %r)' % (self.origin, self.expansion, self.alias, self.options)

    def __hash__(self):
        return self._hash

    def __eq__(self, other):
        if not isinstance(other, Rule):
            return False
        return self.origin == other.origin and self.expansion == other.expansion


class RuleOptions:
    def __init__(self, keep_all_tokens=False, expand1=False, priority=None):
        self.keep_all_tokens = keep_all_tokens
        self.expand1 = expand1
        self.priority = priority
        self.empty_indices = ()

    def __repr__(self):
        return 'RuleOptions(%r, %r, %r)' % (
            self.keep_all_tokens,
            self.expand1,
            self.priority,
        )
