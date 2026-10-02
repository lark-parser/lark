"""This is an experimental tool for reconstructing text from a shaped tree, based on a Lark grammar.
"""

from typing import Dict, Callable, Iterable, Optional

from .lark import Lark
from .tree import Tree, ParseTree
from .visitors import Transformer_InPlace
from .lexer import Token, PatternStr, TerminalDef, Scanner
from .grammar import Terminal, Symbol

from .tree_matcher import TreeMatcher, is_discarded_terminal, parse_rulename
from .utils import is_id_continue, TextSlice

def is_iter_empty(i):
    try:
        _ = next(i)
        return False
    except StopIteration:
        return True


class WriteTokensTransformer(Transformer_InPlace):
    "Inserts discarded tokens into their correct place, according to the rules of grammar"

    tokens: Dict[str, TerminalDef]
    term_subs: Dict[str, Callable[[Symbol], str]]

    def __init__(self, tokens: Dict[str, TerminalDef], term_subs: Dict[str, Callable[[Symbol], str]]) -> None:
        self.tokens = tokens
        self.term_subs = term_subs

    def __default__(self, data, children, meta):
        if not getattr(meta, 'match_tree', False):
            return Tree(data, children)

        iter_args = iter(children)
        to_write = []
        for sym in meta.orig_expansion:
            if is_discarded_terminal(sym):
                try:
                    v = self.term_subs[sym.name](sym)
                except KeyError:
                    t = self.tokens[sym.name]
                    if not isinstance(t.pattern, PatternStr):
                        raise NotImplementedError("Reconstructing regexps not supported yet: %s" % t)

                    v = t.pattern.value
                to_write.append(v)
            else:
                x = next(iter_args)
                if isinstance(x, list):
                    to_write += x
                else:
                    if isinstance(x, Token):
                        assert Terminal(x.type) == sym, x
                    else:
                        name, _args = parse_rulename(sym.name)
                        assert x.data == name, (sym, x)
                        x.meta.orig_rulename = sym.name
                    to_write.append(x)

        assert is_iter_empty(iter_args)
        return to_write


class Reconstructor(TreeMatcher):
    """
    A Reconstructor that will, given a full parse Tree, generate source code.

    Note:
        The reconstructor cannot generate values from regexps. If you need to produce discarded
        regexes, such as newlines, use `term_subs` and provide default values for them.

    Parameters:
        parser: a Lark instance
        term_subs: a dictionary of [Terminal name as str] to [output text as str]
    """

    write_tokens: WriteTokensTransformer

    def __init__(self, parser: Lark, term_subs: Optional[Dict[str, Callable[[Symbol], str]]]=None) -> None:
        TreeMatcher.__init__(self, parser)

        self.write_tokens = WriteTokensTransformer({t.name:t for t in self.tokens}, term_subs or {})
        self._scanner: Optional[Scanner] = None

    @property
    def scanner(self) -> Optional[Scanner]:
        """A scanner over the grammar's terminals, ordered the way the basic lexer orders them,
        so that it reads the output back the way the lexer will.
        """
        if self._scanner is None and self.tokens:
            terminals = sorted(self.tokens, key=lambda t: (-t.priority, -t.pattern.max_width, -len(t.pattern.value), t.name))
            conf = self.parser.lexer_conf
            self._scanner = Scanner(terminals, conf.g_regex_flags, conf.re_module, use_bytes=False)
        return self._scanner

    def _absorbs_next(self, prev_item: str, item: str) -> bool:
        "Whether lexing `prev_item` with `item` appended to it would read past the end of `prev_item`"
        scanner = self.scanner
        if scanner is None:
            return False
        text = prev_item + item
        res = scanner.match(TextSlice(text, 0, len(text)), 0)
        return res is not None and len(res[0]) > len(prev_item)

    def _reconstruct(self, tree, orig_rulename=None):
        unreduced_tree = self.match_tree(tree, orig_rulename or tree.data)

        res = self.write_tokens.transform(unreduced_tree)
        for item in res:
            if isinstance(item, Tree):
                child_rulename = getattr(item.meta, "orig_rulename", None)
                yield from self._reconstruct(item, child_rulename)
            else:
                yield item

    def reconstruct(self, tree: ParseTree, postproc: Optional[Callable[[Iterable[str]], Iterable[str]]]=None, insert_spaces: bool=True) -> str:
        x = self._reconstruct(tree)
        if postproc:
            x = postproc(x)
        y = []
        prev_item = ''
        for item in x:
            if insert_spaces and prev_item and item and (
                    (is_id_continue(prev_item[-1]) and is_id_continue(item[0]))
                    or self._absorbs_next(prev_item, item)):
                y.append(' ')
            y.append(item)
            prev_item = item
        return ''.join(y)
