import re
from setuptools import setup

__version__ ,= re.findall('__version__ = "(.*)"', open('lark/__init__.py').read())

setup(
    name = "lark-parser",
    version = __version__,
    packages = ['lark', 'lark.parsers', 'lark.tools', 'lark.grammars'],

    requires = [],
    install_requires = [],

    package_data = { '': ['*.md', '*.lark'] },

    test_suite = 'tests.__main__',

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

With Lark, you can parse any context-free grammar, efficiently, with very little code.

Main Features:
 - Builds a parse-tree (AST) automagically, based on the structure of the grammar
 - Earley parser
    - Can parse all context-free grammars
    - Full support for ambiguous grammars
 - LALR(1) parser
    - Fast and light, competitive with PLY
    - Can generate a stand-alone parser
 - CYK parser, for highly ambiguous grammars
 - EBNF grammar
 - Unicode fully supported
 - Python 2 & 3 compatible
 - Automatic line & column tracking
 - Standard library of terminals (strings, numbers, names, etc.)
 - Import grammars from Nearley.js
 - Extensive test suite
 - And much more!
''',

    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Text Processing :: General",
        "Topic :: Text Processing :: Linguistic",
        "License :: OSI Approved :: MIT License",
    ],

)

