import re
from setuptools import setup

__version__ ,= re.findall('__version__ = "(.*)"', open('lark/__init__.py').read())

setup(
    name = "lark-parser",
    version = __version__,
    packages = ['lark', 'lark.parsers', 'lark.tools', 'lark.grammars'],

    requires = [],
    install_requires = [],

    package_data = {
        '': ['*.md', '*.g'],
        'docs': ['*.png'],
    },

    # metadata for upload to PyPI
    author = "Erez Shinan",
    author_email = "erezshin@gmail.com",
    description = "a modern parsing library",
    license = "MIT",
    keywords = "Earley LALR parser parsing ast",
    url = "https://github.com/erezsh/lark",
    download_url = "https://github.com/erezsh/lark/tarball/master",
    long_description='''
Lark is a modern general-purpose parsing library for Python.

Lark focuses on simplicity and power. It lets you choose between two parsing algorithms:

Earley : Parses all context-free grammars (even ambiguous ones)! It is the default.
LALR(1): Only LR grammars. Outperforms PLY and most if not all other pure-python parsing libraries.
Both algorithms are written in Python and can be used interchangably with the same grammar (aside for algorithmic restrictions). See "Comparison to other parsers" for more details.

Lark can automagically build an AST from your grammar, without any more code on your part.

Features:

- EBNF grammar with a little extra
- Earley & LALR(1)
- Builds an AST automagically based on the grammar
- Automatic line & column tracking
- Automatic token collision resolution (unless both tokens are regexps)
- Python 2 & 3 compatible
- Unicode fully supported
''',

    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Text Processing :: General",
        "License :: OSI Approved :: MIT License",
    ],

)

