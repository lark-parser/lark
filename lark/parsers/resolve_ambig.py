from ..utils import compare
from functools import cmp_to_key

from ..tree import Tree, Visitor_NoRecurse


# Standard ambiguity resolver (uses comparison)
#
# Author: Erez Sh

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
        try:
            return -compare(tree1, tree2)
        except TypeError:
            return 0

    try:
        rule1, rule2 = tree1.rule, tree2.rule
    except AttributeError:
        # Probably trees that don't take part in this parse (better way to distinguish?)
        return -compare(tree1, tree2)

    # XXX These artifacts can appear due to imperfections in the ordering of Visitor_NoRecurse,
    #     when confronted with duplicate (same-id) nodes. Fixing this ordering is possible, but would be
    #     computationally inefficient. So we handle it here.
    if tree1.data == '_ambig':
        _standard_resolve_ambig(tree1)
    if tree2.data == '_ambig':
        _standard_resolve_ambig(tree2)

    c = _compare_rules(tree1.rule, tree2.rule)
    if c:
        return c

    # rules are "equal", so compare trees
    for t1, t2 in zip(tree1.children, tree2.children):
        c = _compare_drv(t1, t2)
        if c:
            return c

    return compare(len(tree1.children), len(tree2.children))


def _standard_resolve_ambig(tree):
    assert tree.data == '_ambig'
    best = min(tree.children, key=cmp_to_key(_compare_drv))
    assert best.data == 'drv'
    tree.set('drv', best.children)
    tree.rule = best.rule   # needed for applying callbacks

def standard_resolve_ambig(tree):
    for ambig in tree.find_data('_ambig'):
        _standard_resolve_ambig(ambig)

    return tree




# Anti-score Sum
#
# Author: Uriva (https://github.com/uriva)

def _antiscore_sum_drv(tree):
    if not isinstance(tree, Tree):
        return 0

    # XXX These artifacts can appear due to imperfections in the ordering of Visitor_NoRecurse,
    #     when confronted with duplicate (same-id) nodes. Fixing this ordering is possible, but would be
    #     computationally inefficient. So we handle it here.
    if tree.data == '_ambig':
        _antiscore_sum_resolve_ambig(tree)

    try:
        priority = tree.rule.options.priority
    except AttributeError:
        # Probably trees that don't take part in this parse (better way to distinguish?)
        priority = None

    return (priority or 0) + sum(map(_antiscore_sum_drv, tree.children), 0)

def _antiscore_sum_resolve_ambig(tree):
    assert tree.data == '_ambig'

    best = min(tree.children, key=_antiscore_sum_drv)
    assert best.data == 'drv'
    tree.set('drv', best.children)
    tree.rule = best.rule   # needed for applying callbacks

def antiscore_sum_resolve_ambig(tree):
    for ambig in tree.find_data('_ambig'):
        _antiscore_sum_resolve_ambig(ambig)

    return tree
