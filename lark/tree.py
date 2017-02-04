
class Tree(object):
    def __init__(self, data, children):
        self.data = data
        self.children = list(children)

    def __repr__(self):
        return 'Tree(%s, %s)' % (self.data, self.children)

    def _pretty(self, level, indent_str):
        if len(self.children) == 1 and not isinstance(self.children[0], Tree):
            return [ indent_str*level, self.data, '\t', '%s' % self.children[0], '\n']

        l = [ indent_str*level, self.data, '\n' ]
        for n in self.children:
            if isinstance(n, Tree):
                l += n._pretty(level+1, indent_str)
            else:
                l += [ indent_str*(level+1), '%s' % n, '\n' ]

        return l

    def pretty(self, indent_str='  '):
        return ''.join(self._pretty(0, indent_str))

    def expand_kids_by_index(self, *indices):
        for i in sorted(indices, reverse=True): # reverse so that changing tail won't affect indices
            kid = self.children[i]
            self.children[i:i+1] = kid.children


    # def find_path(self, pred):
    #     if pred(self):
    #         yield []
    #     else:
    #         for i, c in enumerate(self.children):
    #             if isinstance(c, Tree):
    #                 for path in c.find_path(pred):
    #                     yield [i] + path

    # def follow_path(self, path):
    #     x = self
    #     for step in path:
    #         x = x.children[step]
    #     return x

    # def set_at_path(self, path, value):
    #     x = self.follow_path(path[:-1])
    #     x.children[path[-1]] = value

    def clone(self):
        return Tree(self.data, [c.clone() if isinstance(c, Tree) else c for c in self.children])


class Transformer(object):
    def transform(self, tree):
        items = [self.transform(c) if isinstance(c, Tree) else c for c in tree.children]
        try:
            f = getattr(self, tree.data)
        except AttributeError:
            return self.__default__(tree.data, items)
        else:
            return f(*items)


    def __default__(self, data, children):
        return Tree(data, children)


class Visitor(object):
    def visit(self, tree):
        for child in tree.children:
            if isinstance(child, Tree):
                self.visit(child)

        f = getattr(self, tree.data, self.__default__)
        f(tree)
        return tree

    def __default__(self, tree):
        pass


