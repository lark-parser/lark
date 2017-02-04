from collections import deque

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

def classify(seq, key=None):
    d = {}
    for item in seq:
        k = key(item) if (key is not None) else item
        if k in d:
            d[k].append(item)
        else:
            d[k] = [item]
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




try:
    STRING_TYPE = basestring
except NameError:   # Python 3
    STRING_TYPE = str

Str = type(u'')


