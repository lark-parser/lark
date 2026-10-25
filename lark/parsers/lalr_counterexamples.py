"""Lookahead-sensitive derivations explaining LALR conflicts.

See Isradisaikul and Myers, Finding Counterexamples from Parsing Conflicts,
section 4: https://www.cs.cornell.edu/andru/papers/cupex/cupex.pdf
"""

from collections import deque
from copy import deepcopy

from ..grammar import Terminal
from ..tree import Tree
from .grammar_analysis import RulePtr, calculate_sets


_END = Terminal('$END')
_DOT = object()


class CounterexampleGenerator:
    def __init__(self, analyzer, max_nodes=10000):
        self.max_nodes = max_nodes
        all_rules = [r for group in analyzer.lr0_rules_by_origin.values() for r in group]
        productive = {s for rule in all_rules for s in rule.expansion if s.is_term}
        while True:
            origins = {r.origin for r in all_rules if all(s in productive for s in r.expansion)}
            if origins <= productive:
                break
            productive.update(origins)
        self.rules = {
            origin: [rule for rule in group if all(s in productive for s in rule.expansion)]
            for origin, group in analyzer.lr0_rules_by_origin.items() if origin in productive
        }
        rules = [r for group in self.rules.values() for r in group]
        self.first, self.nullable = analyzer.FIRST, analyzer.NULLABLE
        if len(rules) != len(all_rules):
            self.first, _, self.nullable = calculate_sets(rules)
        self.roots = [
            (state, next(iter(state.kernel)), _END, 0)
            for _, state in sorted(analyzer.lr0_start_states.items())
            if next(iter(state.kernel)).rule.origin in productive
        ]
        self.empty = self._derive_empty()
        self.leading = {}

    @staticmethod
    def _rule_key(rule):
        return rule.origin.name, tuple(s.name for s in rule.expansion)

    def _follow(self, item, lookahead):
        result = set()
        for symbol in item.rule.expansion[item.index + 1:]:
            result.update(self.first[symbol])
            if symbol not in self.nullable:
                break
        else:
            result.add(lookahead)
        return sorted(result, key=lambda s: s.name)

    def _successors(self, node, prefix):
        state, item, follow, position = node
        if item.is_satisfied:
            return
        symbol = item.next
        if prefix is None or (position < len(prefix) and symbol == prefix[position]):
            next_position = position + 1 if prefix is not None else 0
            yield (state.transitions[symbol], item.advance(symbol), follow, next_position), symbol
        if not symbol.is_term:
            follows = self._follow(item, follow)
            for rule in sorted(self.rules[symbol], key=self._rule_key):
                for lookahead in follows:
                    yield (state, RulePtr(rule, 0), lookahead, position), None

    def _path(self, target_state, lookahead, rule=None, prefix=None, roots=None):
        queue = deque(self.roots if roots is None else roots)
        previous = dict.fromkeys(queue)
        while queue and len(previous) <= self.max_nodes:
            node = queue.popleft()
            state, item, follow, position = node
            if state is target_state and (prefix is None or position == len(prefix)):
                if rule is None:
                    found = not item.is_satisfied and item.next == lookahead
                else:
                    found = item.rule == rule and item.is_satisfied and follow == lookahead
                if found:
                    path = []
                    while previous[node] is not None:
                        parent, edge = previous[node]
                        path.append((node, edge))
                        node = parent
                    path.append((node, None))
                    return list(reversed(path))

            for child, edge in self._successors(node, prefix):
                if child not in previous:
                    if len(previous) >= self.max_nodes:
                        break
                    previous[child] = node, edge
                    queue.append(child)
        return None

    def _derive_empty(self):
        derivations = {}
        rules = sorted((r for group in self.rules.values() for r in group), key=self._rule_key)
        changed = True
        while changed:
            changed = False
            for rule in rules:
                if not all(s in derivations for s in rule.expansion):
                    continue
                cost = 1 + sum(derivations[s][0] for s in rule.expansion)
                if rule.origin not in derivations or cost < derivations[rule.origin][0]:
                    children = [derivations[s][1] for s in rule.expansion]
                    derivations[rule.origin] = cost, Tree(rule.origin.name, children)
                    changed = True
        return derivations

    def _derive_leading(self, lookahead):
        if lookahead in self.leading:
            return self.leading[lookahead]
        derivations = {lookahead: (0, lookahead)}
        rules = sorted((r for group in self.rules.values() for r in group), key=self._rule_key)
        changed = True
        while changed:
            changed = False
            for rule in rules:
                before = []
                prefix_cost = 0
                for index, symbol in enumerate(rule.expansion):
                    if symbol in derivations:
                        cost, child = derivations[symbol]
                        cost += 1 + prefix_cost
                        if rule.origin not in derivations or cost < derivations[rule.origin][0]:
                            children = before + [child] + list(rule.expansion[index + 1:])
                            derivations[rule.origin] = cost, Tree(rule.origin.name, children)
                            changed = True
                    if symbol not in self.empty:
                        break
                    cost, child = self.empty[symbol]
                    prefix_cost += cost
                    before.append(child)
        self.leading[lookahead] = derivations
        return derivations

    @staticmethod
    def _tree(path):
        root_rule = path[0][0][1].rule
        root = current = Tree(root_rule.origin.name, list(root_rule.expansion))
        previous_item = path[0][0][1]
        for (_, item, _, _), edge in path[1:]:
            if edge is None:
                child = Tree(item.rule.origin.name, list(item.rule.expansion))
                current.children[previous_item.index] = child
                current = child
            previous_item = item
        current.children.insert(previous_item.index, _DOT)
        return root.children[0]

    @staticmethod
    def _leaves(tree):
        stack = [(tree, i) for i in reversed(range(len(tree.children)))]
        while stack:
            parent, index = stack.pop()
            child = parent.children[index]
            if isinstance(child, Tree):
                stack.extend((child, i) for i in reversed(range(len(child.children))))
            else:
                yield parent, index, child

    def _complete(self, tree, lookahead):
        after_dot = False
        leading = self._derive_leading(lookahead)
        for parent, index, symbol in self._leaves(tree):
            if symbol is _DOT:
                after_dot = True
            elif after_dot:
                if symbol == lookahead:
                    return tree
                if lookahead != _END and symbol in leading:
                    parent.children[index] = deepcopy(leading[symbol][1])
                    return tree
                if symbol not in self.empty:
                    return None
                parent.children[index] = deepcopy(self.empty[symbol][1])
        return tree if lookahead == _END else None

    def _within_budget(self, tree):
        stack = [tree]
        for _ in range(self.max_nodes):
            if not stack:
                return True
            node = stack.pop()
            if isinstance(node, Tree):
                stack.extend(node.children)
        return not stack

    @classmethod
    def _display_tree(cls, tree):
        return Tree(tree.data, [
            cls._display_tree(child) if isinstance(child, Tree)
            else '*' if child is _DOT else child.name
            for child in tree.children
        ])

    def generate(self, state, lookahead, rule, other_rule=None):
        """Return two lookahead-valid derivations, or None if no pair is found.

        Production edges retain the precise lookahead, rather than the merged
        LALR lookahead set. This avoids presenting a spurious ambiguity when
        two LR(1) contexts have been merged into one LALR state.
        """
        first = self._path(state, lookahead, rule)
        if first is None:
            return None
        prefix = tuple(edge for _, edge in first if edge is not None)
        second = self._path(state, lookahead, other_rule, prefix, roots=[first[0][0]])
        if second is None:
            second = self._path(state, lookahead, other_rule, prefix)
        if second is None:
            second = self._path(state, lookahead, other_rule)
        if second is None:
            return None
        trees = [self._complete(self._tree(path), lookahead) for path in (first, second)]
        if any(tree is None or not self._within_budget(tree) for tree in trees):
            return None
        for tree in trees:
            after_dot = False
            for parent, index, symbol in self._leaves(tree):
                if symbol is _DOT:
                    after_dot = True
                elif after_dot and symbol in self.empty:
                    parent.children[index] = deepcopy(self.empty[symbol][1])
            if not self._within_budget(tree):
                return None
        return trees

    def explain(self, state, lookahead, rule, other_rule=None):
        trees = self.generate(state, lookahead, rule, other_rule)
        if trees is None:
            return ''
        examples = [tuple('*' if symbol is _DOT else symbol.name
                          for _, _, symbol in self._leaves(tree)) for tree in trees]
        labels = ('Reduce', 'Shift' if other_rule is None else 'Reduce')
        lines = []
        shared_example = examples[0] == examples[1] and trees[0].data == trees[1].data
        if shared_example:
            lines.append('Example: ' + ' '.join(examples[0]))
        for label, example, tree in zip(labels, examples, trees):
            if not shared_example:
                lines.append(label + ' example: ' + ' '.join(example))
            lines.append(label + ' derivation:\n' + self._display_tree(tree).pretty())
        return '\n'.join(lines)
