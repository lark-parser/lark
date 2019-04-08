import sys
from collections import deque

Py36 = (sys.version_info[:2] >= (3, 6))

class fzset(frozenset):
    def __repr__(self):
        return '{%s}' % ', '.join(map(repr, self))


def classify_bool(seq, pred):
    true_elems = []
    false_elems = []

    for elem in seq:
        if pred(elem):
            true_elems.append(elem)
        else:
            false_elems.append(elem)

    return true_elems, false_elems

def classify(seq, key=None, value=None):
    d = {}
    for item in seq:
        k = key(item) if (key is not None) else item
        v = value(item) if (value is not None) else item
        if k in d:
            d[k].append(v)
        else:
            d[k] = [v]
    return d

def bfs(initial, expand):
    open_q = deque(list(initial))
    visited = set(open_q)
    while open_q:
        node = open_q.popleft()
        yield node
        for next_node in expand(node):
            if next_node not in visited:
                visited.add(next_node)
                open_q.append(next_node)



def _serialize(value):
    if isinstance(value, Serialize):
        return value.serialize()
    elif isinstance(value, list):
        return [_serialize(elem) for elem in value]
    elif isinstance(value, frozenset):
        return list(value)  # TODO reversible?
    elif isinstance(value, dict):
        return {key:_serialize(elem) for key, elem in value.items()}
    return value

def _deserialize(data, namespace):
    if isinstance(data, dict):
        if '__type__' in data: # Object
            class_ = namespace[data['__type__']]
            return class_.deserialize(data)
        return {key:_deserialize(value, namespace) for key, value in data.items()}
    elif isinstance(data, list):
        return [_deserialize(value, namespace) for value in data]
    return data


class Serialize(object):
    def serialize(self):
        fields = getattr(self, '__serialize_fields__')
        res = {f: _serialize(getattr(self, f)) for f in fields}
        res['__type__'] = type(self).__name__
        postprocess = getattr(self, '_serialize', None)
        if postprocess:
            postprocess(res)
        return res

    @classmethod
    def deserialize(cls, data):
        namespace = getattr(cls, '__serialize_namespace__', dict)
        namespace = {c.__name__:c for c in namespace()}

        fields = getattr(cls, '__serialize_fields__')

        inst = cls.__new__(cls)
        for f in fields:
            setattr(inst, f, _deserialize(data[f], namespace))
        postprocess = getattr(inst, '_deserialize', None)
        if postprocess:
            postprocess()
        return inst



###{standalone
try:
    STRING_TYPE = basestring
except NameError:   # Python 3
    STRING_TYPE = str


import types
from functools import wraps, partial
from contextlib import contextmanager

Str = type(u'')
try:
    classtype = types.ClassType # Python2
except AttributeError:
    classtype = type    # Python3

def smart_decorator(f, create_decorator):
    if isinstance(f, types.FunctionType):
        return wraps(f)(create_decorator(f, True))

    elif isinstance(f, (classtype, type, types.BuiltinFunctionType)):
        return wraps(f)(create_decorator(f, False))

    elif isinstance(f, types.MethodType):
        return wraps(f)(create_decorator(f.__func__, True))

    elif isinstance(f, partial):
        # wraps does not work for partials in 2.7: https://bugs.python.org/issue3445
        return create_decorator(f.__func__, True)

    else:
        return create_decorator(f.__func__.__call__, True)

def dedup_list(l):
    """Given a list (l) will removing duplicates from the list,
       preserving the original order of the list. Assumes that
       the list entrie are hashable."""
    dedup = set()
    return [ x for x in l if not (x in dedup or dedup.add(x))]

###}


try:
    from contextlib import suppress     # Python 3
except ImportError:
    @contextmanager
    def suppress(*excs):
        '''Catch and dismiss the provided exception

        >>> x = 'hello'
        >>> with suppress(IndexError):
        ...     x = x[10]
        >>> x
        'hello'
        '''
        try:
            yield
        except excs:
            pass




try:
    compare = cmp
except NameError:
    def compare(a, b):
        if a == b:
            return 0
        elif a > b:
            return 1
        return -1


import sre_parse
import sre_constants
def get_regexp_width(regexp):
    try:
        return sre_parse.parse(regexp).getwidth()
    except sre_constants.error:
        raise ValueError(regexp)


class Enumerator:
    def __init__(self):
        self.enums = {}

    def get(self, item):
        if item not in self.enums:
            self.enums[item] = len(self.enums)
        return self.enums[item]

    def __len__(self):
        return len(self.enums)

    def reversed(self):
        r = {v: k for k, v in self.enums.items()}
        assert len(r) == len(self.enums)
        return r

