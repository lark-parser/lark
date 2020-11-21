from __future__ import print_function

###{standalone
#
#
#   Lark Stand-alone Generator Tool
# ----------------------------------
# Generates a stand-alone LALR(1) parser with a standard lexer
#
# Git:    https://github.com/erezsh/lark
# Author: Erez Shinan (erezshin@gmail.com)
#
#
#    >>> LICENSE
#
#    This tool and its generated code use a separate license from Lark,
#    and are subject to the terms of the Mozilla Public License, v. 2.0.
#    If a copy of the MPL was not distributed with this
#    file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
#    If you wish to purchase a commercial license for this tool and its
#    generated code, you may contact me via email or otherwise.
#
#    If MPL2 is incompatible with your free or open-source project,
#    contact me and we'll work it out.
#
#

from io import open

###}

import sys
import token, tokenize
import os
from os import path
from collections import defaultdict
from functools import partial
from argparse import ArgumentParser, SUPPRESS
from warnings import warn

import lark
from lark import Lark
from lark.tools import lalr_argparser, build_lalr, make_warnings_comments


from lark.grammar import RuleOptions, Rule
from lark.lexer import TerminalDef

_dir = path.dirname(__file__)
_larkdir = path.join(_dir, path.pardir)


EXTRACT_STANDALONE_FILES = [
    "tools/standalone.py",
    "exceptions.py",
    "utils.py",
    "tree.py",
    "visitors.py",
    "indenter.py",
    "grammar.py",
    "lexer.py",
    "common.py",
    "parse_tree_builder.py",
    "parsers/lalr_parser.py",
    "parsers/lalr_analysis.py",
    "parser_frontends.py",
    "lark.py",
]


def extract_sections(lines):
    section = None
    text = []
    sections = defaultdict(list)
    for l in lines:
        if l.startswith("###"):
            if l[3] == "{":
                section = l[4:].strip()
            elif l[3] == "}":
                sections[section] += text
                section = None
                text = []
            else:
                raise ValueError(l)
        elif section:
            text.append(l)

    return {name: "".join(text) for name, text in sections.items()}


def strip_docstrings(line_gen):
    """Strip comments and docstrings from a file.
    Based on code from: https://stackoverflow.com/questions/1769332/script-to-remove-python-comments-docstrings
    """
    res = []

    prev_toktype = token.INDENT
    last_lineno = -1
    last_col = 0

    tokgen = tokenize.generate_tokens(line_gen)
    for toktype, ttext, (slineno, scol), (elineno, ecol), ltext in tokgen:
        if slineno > last_lineno:
            last_col = 0
        if scol > last_col:
            res.append(" " * (scol - last_col))
        if toktype == token.STRING and prev_toktype == token.INDENT:
            # Docstring
            res.append("#--")
        elif toktype == tokenize.COMMENT:
            # Comment
            res.append("##\n")
        else:
            res.append(ttext)
        prev_toktype = toktype
        last_col = ecol
        last_lineno = elineno

    return "".join(res)


def main(fobj, start, print=print):
    warn(
        "`lark.tools.standalone.main` is being redesigned. Use `gen_standalone`",
        DeprecationWarning,
    )
    lark_inst = Lark(fobj, parser="lalr", lexer="contextual", start=start)
    gen_standalone(lark_inst, print)


def gen_standalone(lark_inst, output=None, out=sys.stdout, compress=False):
    if output is None:
        output = partial(print, file=out)

    import pickle, zlib, base64

    def compressed_output(obj):
        s = pickle.dumps(obj, pickle.HIGHEST_PROTOCOL)
        c = zlib.compress(s)
        output(repr(base64.b64encode(c)))

    def output_decompress(name):
        output(
            "%(name)s = pickle.loads(zlib.decompress(base64.b64decode(%(name)s)))"
            % locals()
        )

    output("# The file was automatically generated by Lark v%s" % lark.__version__)
    output('__version__ = "%s"' % lark.__version__)
    output()

    for i, pyfile in enumerate(EXTRACT_STANDALONE_FILES):
        with open(os.path.join(_larkdir, pyfile)) as f:
            code = extract_sections(f)["standalone"]
            if i:  # if not this file
                code = strip_docstrings(partial(next, iter(code.splitlines(True))))
            output(code)

    data, m = lark_inst.memo_serialize([TerminalDef, Rule])
    output("import pickle, zlib, base64")
    if compress:
        output("DATA = (")
        compressed_output(data)
        output(")")
        output_decompress("DATA")
        output("MEMO = (")
        compressed_output(m)
        output(")")
        output_decompress("MEMO")
    else:
        output("DATA = (")
        output(data)
        output(")")
        output("MEMO = (")
        output(m)
        output(")")

    output("Shift = 0")
    output("Reduce = 1")
    output("def Lark_StandAlone(**kwargs):")
    output("  return Lark._load_from_dict(DATA, MEMO, **kwargs)")


def main():
    make_warnings_comments()
    parser = ArgumentParser(
        prog="prog='python -m lark.tools.standalone'",
        description="Lark Stand-alone Generator Tool",
        parents=[lalr_argparser],
        epilog="Look at the Lark documentation for more info on the options",
    )
    parser.add_argument("old_start", nargs="?", help=SUPPRESS)
    parser.add_argument(
        "-c", "--compress", action="store_true", default=0, help="Enable compression"
    )
    ns = parser.parse_args()
    if ns.old_start is not None:
        warn(
            "The syntax `python -m lark.tools.standalone <grammar-file> <start>` is deprecated. Use the -s option"
        )
        ns.start.append(ns.old_start)

    lark_inst, out = build_lalr(ns)
    gen_standalone(lark_inst, out=out, compress=ns.compress)


if __name__ == "__main__":
    main()
