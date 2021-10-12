"""
Creating URL Parser from ABNF grammar in internet standards (RFCs)
==================================================================

Usage:
 python3 -m examples.url_parser_abnf https://github.com/lark%2Dparser/lark
 python3 -m examples.url_parser_abnf http://user@127.0.0.1:8000/index.html

It outputs parse tree for an URI passed as first argument.

"""
import sys

from lark import Lark, Transformer, v_args, abnf_alias, Token, Visitor, Tree

grammar_in_abnf ="""
%import .grammars.rfc3986   ; import from ./grammars/rfc3986.abnf
%import core-rules          ; import from the standard library: ../lark/grammars/core-rules.abnf
"""


class SimplifyABNFTree_Visitor(Visitor):
    def __init__(self, unwrap_children=(), keep=(), *args, **kwargs):
        super(SimplifyABNFTree_Visitor, self).__init__(*args, **kwargs)
        self.unwrap = unwrap_children
        self.keep   = keep

    def visit(self, tree: Tree) -> Tree:
        # override self.visit(), since _unwrap_and_flatten() assumes top-down visitor
        self.visit_topdown(tree)

    def _unwrap_and_flatten(self, tree, unwrap_recursive=False):
        """ a generator to flatten tree into list or tuple """
        do_unwrap = True if tree.data in self.unwrap or unwrap_recursive else False

        for x in tree.children:
            if isinstance(x, Tree) and do_unwrap:
                if x.data in self.keep:
                    yield self._concat_tokens(x, unwrap_recursive=True)
                else:
                    for item in list(self._unwrap_and_flatten(x, unwrap_recursive=True)):
                        yield item
            elif isinstance(x, Token):
                yield x
            else:
                yield x


    def _concat_tokens(self, tree, unwrap_recursive=False):
        """ concatenate multiple tokens in tree.children into single token.
            leave it as it is if there is a tree in tree.children.
        """
        items = [None]
        words = []
        children = list(self._unwrap_and_flatten(tree, unwrap_recursive=unwrap_recursive))

        for x in children:
            if isinstance(x, Token):
                words.append(x.value)
                if not isinstance(items[-1], Token):
                    items.append(x)
            else:
                if len(words) > 1:
                    items[-1] = items[-1].update(value=''.join(words))
                items.append(x)
                words=[]

        if len(words) > 1:
            items[-1] = items[-1].update(value=''.join(words))

        tree.children = items[1:]
        return tree;

    def __default__(self, tree):
        return self._concat_tokens(tree)


@abnf_alias
class pct_encoded_conv(Transformer):
    def pct_encoded(self, items): # alias for pct-encoded
        # items = "%" HEXDIG HEXDIG

        # extract hexadecimal digits, convert it to a character,
        # then return modified token
        char_in_hex = ''.join((items[1].children[0], items[2].children[0]))
        char_ = bytearray.fromhex(char_in_hex).decode()
        token = items[0].update(value=char_)
        return token

def main():
    url = sys.argv[1]

    url_parser = Lark(grammar_in_abnf,
                      # using ABNF grammar
                      syntax='abnf',
                      start='URI',
                      # use earley parser since RFC3986 is too complex for LALR.
                      parser='earley',
                      # usually needed to set keep_all_tokens=True when ABNF grammar is used.
                      keep_all_tokens=True,
    )
    tree = url_parser.parse(url)

    # Convert pct-encoded (e.g. '%2D' in given URL) to ascii characters
    transformer=pct_encoded_conv()
    tree = transformer.transform(tree)

    # We need some post-processing to unwrap unwanted tree node and concatenate ABNF tokens
    # to construct a token that we actually want since many ABNF grammar
    # in RFCs split every input into too small units like a single character.
    unwrap = ('scheme', 'userinfo', 'IPv4address', 'IPv6address', 'reg-name',
              'path-abempty', 'path-absolute', 'path-noscheme', 'path-rootless')
    simplifier = SimplifyABNFTree_Visitor(unwrap_children=unwrap)
    simplifier.visit(tree)

    print(tree.pretty())


if __name__ == '__main__':
    main()
