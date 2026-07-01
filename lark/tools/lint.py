"""
Lark Grammar Linter
"""

import sys
import argparse
from typing import Set

from lark.grammar import NonTerminal, Terminal
from lark.load_grammar import load_grammar
from lark.exceptions import GrammarError
import os

def lint_grammar(grammar_text: str, filename: str = '<string>', import_paths=None) -> int:
    """
    Lints a grammar and prints warnings.
    Returns the number of warnings found.
    """
    if import_paths is None:
        import_paths = []
        if filename != '<string>':
            import_paths.append(os.path.dirname(filename))

    try:
        g, _ = load_grammar(grammar_text, filename, import_paths, False)
    except GrammarError as e:
        print(f"{filename}: warning: {e}")
        return 1
    
    used_rules: Set[str] = set()
    used_terms: Set[str] = set()
    
    for name, params, tree, options in g.rule_defs:
        for node in tree.iter_subtrees():
            for child in node.children:
                if isinstance(child, NonTerminal):
                    used_rules.add(child.name)
                elif isinstance(child, Terminal):
                    used_terms.add(child.name)
    
    for name, (term_tree, priority) in g.term_defs:
        if term_tree is not None:
            for node in term_tree.iter_subtrees():
                for child in node.children:
                    if isinstance(child, NonTerminal):
                        used_rules.add(child.name)
                    elif isinstance(child, Terminal):
                        used_terms.add(child.name)
                        
    for ignore_term in g.ignore:
        used_terms.add(ignore_term)

    defined_rules = {str(name) for name, params, tree, options in g.rule_defs}
    defined_terms = {str(name) for name, (term_tree, priority) in g.term_defs}
    
    warnings = 0
    
    # Start rule is used by default if it's defined
    if 'start' in defined_rules:
        used_rules.add('start')
        
    unused_rules = defined_rules - used_rules
    for rule in sorted(unused_rules):
        print(f"{filename}: warning: Unused rule '{rule}'")
        warnings += 1
        
    unused_terms = defined_terms - used_terms
    for term in sorted(unused_terms):
        print(f"{filename}: warning: Unused terminal '{term}'")
        warnings += 1
        
    return warnings

def main():
    parser = argparse.ArgumentParser(description="Lark Grammar Linter")
    parser.add_argument("grammar_file", type=argparse.FileType('r'), help="Path to the grammar file to lint")
    args = parser.parse_args()
    
    grammar_text = args.grammar_file.read()
    filename = args.grammar_file.name
    args.grammar_file.close()
    
    warnings = lint_grammar(grammar_text, filename)
    
    if warnings > 0:
        sys.exit(1)
    else:
        sys.exit(0)

if __name__ == '__main__':
    main()
