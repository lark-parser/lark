from ..utils import compare
from functools import cmp_to_key

from ..tree import Tree, Visitor_NoRecurse

def _compare_rules(rule1, rule2):
    if rule1.origin != rule2.origin:
        if rule1.options and rule2.options:
            if rule1.options.priority is not None and rule2.options.priority is not None:
                assert rule1.options.priority != rule2.options.priority, "Priority is the same between both rules: %s == %s" % (rule1, rule2)
                return -compare(rule1.options.priority, rule2.options.priority)

        return 0

    c = compare( len(rule1.expansion), len(rule2.expansion))
    if rule1.origin.startswith('__'):   # XXX hack! We need to set priority in parser, not here
        c = -c
    return c

def _compare_drv(tree1, tree2):
    if not (isinstance(tree1, Tree) and isinstance(tree2, Tree)):
        return -compare(tree1, tree2)

    try:
        rule1, rule2 = tree1.rule, tree2.rule
    except AttributeError:
        # Probably trees that don't take part in this parse (better way to distinguish?)
        return -compare(tree1, tree2)

    # XXX These artifacts can appear due to imperfections in the ordering of Visitor_NoRecurse,
    #     when confronted with duplicate (same-id) nodes. Fixing this ordering is possible, but would be
    #     computationally inefficient. So we handle it here.
    if tree1.data == '_ambig':
        _resolve_ambig(tree1)
    if tree2.data == '_ambig':
        _resolve_ambig(tree2)

    c = _compare_rules(tree1.rule, tree2.rule)
    if c:
        return c

    # rules are "equal", so compare trees
    for t1, t2 in zip(tree1.children, tree2.children):
        c = _compare_drv(t1, t2)
        if c:
            return c

    return compare(len(tree1.children), len(tree2.children))


def _resolve_ambig(tree):
    assert tree.data == '_ambig'

    best = min(tree.children, key=cmp_to_key(_compare_drv))
    assert best.data == 'drv'
    tree.set('drv', best.children)
    tree.rule = best.rule   # needed for applying callbacks

    assert tree.data != '_ambig'

class ResolveAmbig(Visitor_NoRecurse):
    def _ambig(self, tree):
        _resolve_ambig(tree)


def resolve_ambig(tree):
    ResolveAmbig().visit(tree)
    return tree
