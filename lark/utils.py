import unicodedata
import os
from functools import reduce
from collections import deque

###{standalone
import sys, re
import logging
logger: logging.Logger = logging.getLogger("lark")
logger.addHandler(logging.StreamHandler())
# Set to highest level, since we have some warnings amongst the code
# By default, we should not output any log messages
logger.setLevel(logging.CRITICAL)


NO_VALUE = object()


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


def _deserialize(data, namespace, memo):
    if isinstance(data, dict):
        if '__type__' in data:  # Object
            class_ = namespace[data['__type__']]
            return class_.deserialize(data, memo)
        elif '@' in data:
            return memo[data['@']]
        return {key:_deserialize(value, namespace, memo) for key, value in data.items()}
    elif isinstance(data, list):
        return [_deserialize(value, namespace, memo) for value in data]
    return data


class Serialize:
    """Safe-ish serialization interface that doesn't rely on Pickle

    Attributes:
        __serialize_fields__ (List[str]): Fields (aka attributes) to serialize.
        __serialize_namespace__ (list): List of classes that deserialization is allowed to instantiate.
                                        Should include all field types that aren't builtin types.
    """

    def memo_serialize(self, types_to_memoize):
        memo = SerializeMemoizer(types_to_memoize)
        return self.serialize(memo), memo.serialize()

    def serialize(self, memo=None):
        if memo and memo.in_types(self):
            return {'@': memo.memoized.get(self)}

        fields = getattr(self, '__serialize_fields__')
        res = {f: _serialize(getattr(self, f), memo) for f in fields}
        res['__type__'] = type(self).__name__
        if hasattr(self, '_serialize'):
            self._serialize(res, memo)
        return res

    @classmethod
    def deserialize(cls, data, memo):
        namespace = getattr(cls, '__serialize_namespace__', [])
        namespace = {c.__name__:c for c in namespace}

        fields = getattr(cls, '__serialize_fields__')

        if '@' in data:
            return memo[data['@']]

        inst = cls.__new__(cls)
        for f in fields:
            try:
                setattr(inst, f, _deserialize(data[f], namespace, memo))
            except KeyError as e:
                raise KeyError("Cannot find key for class", cls, e)

        if hasattr(inst, '_deserialize'):
            inst._deserialize()

        return inst


class SerializeMemoizer(Serialize):
    "A version of serialize that memoizes objects to reduce space"

    __serialize_fields__ = 'memoized',

    def __init__(self, types_to_memoize):
        self.types_to_memoize = tuple(types_to_memoize)
        self.memoized = Enumerator()

    def in_types(self, value):
        return isinstance(value, self.types_to_memoize)

    def serialize(self):
        return _serialize(self.memoized.reversed(), None)

    @classmethod
    def deserialize(cls, data, namespace, memo):
        return _deserialize(data, namespace, memo)


try:
    import regex  # type: ignore
except ImportError:
    regex = None

import sre_parse
import sre_constants
categ_pattern = re.compile(r'\\p{[A-Za-z_]+}')

def get_regexp_width(expr):
    if regex:
        # Since `sre_parse` cannot deal with Unicode categories of the form `\p{Mn}`, we replace these with
        # a simple letter, which makes no difference as we are only trying to get the possible lengths of the regex
        # match here below.
        regexp_final = re.sub(categ_pattern, 'A', expr)
    else:
        if re.search(categ_pattern, expr):
            raise ImportError('`regex` module must be installed in order to use Unicode categories.', expr)
        regexp_final = expr
    try:
        return [int(x) for x in sre_parse.parse(regexp_final).getwidth()]
    except sre_constants.error:
        if not regex:
            raise ValueError(expr)
        else:
            # sre_parse does not support the new features in regex. To not completely fail in that case,
            # we manually test for the most important info (whether the empty string is matched)
            c = regex.compile(regexp_final)
            if c.match('') is None:
                # MAXREPEAT is a none pickable subclass of int, therefore needs to be converted to enable caching
                return 1, int(sre_constants.MAXREPEAT)
            else:
                return 0, int(sre_constants.MAXREPEAT)

###}


_ID_START =    'Lu', 'Ll', 'Lt', 'Lm', 'Lo', 'Mn', 'Mc', 'Pc'
_ID_CONTINUE = _ID_START + ('Nd', 'Nl',)

def _test_unicode_category(s, categories):
    if len(s) != 1:
        return all(_test_unicode_category(char, categories) for char in s)
    return s == '_' or unicodedata.category(s) in categories

def is_id_continue(s):
    """
    Checks if all characters in `s` are alphanumeric characters (Unicode standard, so diacritics, indian vowels, non-latin
    numbers, etc. all pass). Synonymous with a Python `ID_CONTINUE` identifier. See PEP 3131 for details.
    """
    return _test_unicode_category(s, _ID_CONTINUE)

def is_id_start(s):
    """
    Checks if all characters in `s` are alphabetic characters (Unicode standard, so diacritics, indian vowels, non-latin
    numbers, etc. all pass). Synonymous with a Python `ID_START` identifier. See PEP 3131 for details.
    """
    return _test_unicode_category(s, _ID_START)


def dedup_list(l):
    """Given a list (l) will removing duplicates from the list,
       preserving the original order of the list. Assumes that
       the list entries are hashable."""
    dedup = set()
    return [x for x in l if not (x in dedup or dedup.add(x))]


class Enumerator(Serialize):
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



def combine_alternatives(lists):
    """
    Accepts a list of alternatives, and enumerates all their possible concatinations.

    Examples:
        >>> combine_alternatives([range(2), [4,5]])
        [[0, 4], [0, 5], [1, 4], [1, 5]]

        >>> combine_alternatives(["abc", "xy", '$'])
        [['a', 'x', '$'], ['a', 'y', '$'], ['b', 'x', '$'], ['b', 'y', '$'], ['c', 'x', '$'], ['c', 'y', '$']]

        >>> combine_alternatives([])
        [[]]
    """
    if not lists:
        return [[]]
    assert all(l for l in lists), lists
    init = [[x] for x in lists[0]]
    return reduce(lambda a,b: [i+[j] for i in a for j in b], lists[1:], init)


try:
    import atomicwrites
except ImportError:
    atomicwrites = None  # type: ignore[assigment]

class FS:
    exists = staticmethod(os.path.exists)

    @staticmethod
    def open(name, mode="r", **kwargs):
        if atomicwrites and "w" in mode:
            return atomicwrites.atomic_write(name, mode=mode, overwrite=True, **kwargs)
        else:
            return open(name, mode, **kwargs)



def isascii(s):
    """ str.isascii only exists in python3.7+ """
    try:
        return s.isascii()
    except AttributeError:
        try:
            s.encode('ascii')
            return True
        except (UnicodeDecodeError, UnicodeEncodeError):
            return False


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

def bfs_all_unique(initial, expand):
    "bfs, but doesn't keep track of visited (aka seen), because there can be no repetitions"
    open_q = deque(list(initial))
    while open_q:
        node = open_q.popleft()
        yield node
        open_q += expand(node)


def _serialize(value, memo):
    if isinstance(value, Serialize):
        return value.serialize(memo)
    elif isinstance(value, list):
        return [_serialize(elem, memo) for elem in value]
    elif isinstance(value, frozenset):
        return list(value)  # TODO reversible?
    elif isinstance(value, dict):
        return {key:_serialize(elem, memo) for key, elem in value.items()}
    # assert value is None or isinstance(value, (int, float, str, tuple)), value
    return value




def small_factors(n, max_factor):
    """
    Splits n up into smaller factors and summands <= max_factor.
    Returns a list of [(a, b), ...]
    so that the following code returns n:

    n = 1
    for a, b in values:
        n = n * a + b

    Currently, we also keep a + b <= max_factor, but that might change
    """
    assert n >= 0
    assert max_factor > 2
    if n <= max_factor:
        return [(n, 0)]

    for a in range(max_factor, 1, -1):
        r, b = divmod(n, a)
        if a + b <= max_factor:
            return small_factors(r, max_factor) + [(a, b)]
    assert False, "Failed to factorize %s" % n
