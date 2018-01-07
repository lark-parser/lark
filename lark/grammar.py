
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

    def __str__(self):
        return '<%s : %s>' % (self.origin, ' '.join(map(str,self.expansion)))

    def __repr__(self):
        return 'Rule(%r, %r, %r, %r)' % (self.origin, self.expansion, self.alias, self.options)


class RuleOptions:
    def __init__(self, keep_all_tokens=False, expand1=False, create_token=None, filter_out=False, priority=None):
        self.keep_all_tokens = keep_all_tokens
        self.expand1 = expand1
        self.create_token = create_token  # used for scanless postprocessing
        self.priority = priority

        self.filter_out = filter_out        # remove this rule from the tree
                                            # used for "token"-rules in scanless
    @classmethod
    def from_rule(cls, name, *x):
        if len(x) > 1:
            priority, expansions = x
            priority = int(priority)
        else:
            expansions ,= x
            priority = None

        keep_all_tokens = name.startswith('!')
        name = name.lstrip('!')
        expand1 = name.startswith('?')
        name = name.lstrip('?')

        return name, expansions, cls(keep_all_tokens, expand1, priority=priority)

    def __repr__(self):
        return 'RuleOptions(%r, %r, %r, %r, %r)' % (
            self.keep_all_tokens,
            self.expand1,
            self.create_token,
            self.priority,
            self.filter_out
        )
