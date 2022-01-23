import re
from setuptools import setup

__version__ ,= re.findall('__version__: str = "(.*)"', open('lark/__init__.py').read())

setup(
    name = "lark",
    version = __version__,
    packages = ['lark', 'lark.parsers', 'lark.tools', 'lark.grammars', 'lark.__pyinstaller'],

    requires = [],
    install_requires = [],

    extras_require = {
        "regex": ["regex"],
        "nearley": ["js2py"],
        "atomic_cache": ["atomicwrites"],
    },

    package_data = {'': ['*.md', '*.lark'], 'lark': ['py.typed']},

    test_suite = 'tests.__main__',

    # metadata for upload to PyPI
    author = "Erez Shinan",
    author_email = "erezshin@gmail.com",
    description = "a modern parsing library",
    license = "MIT",
    keywords = "Earley LALR parser parsing ast",
    url = "https://github.com/lark-parser/lark",
    download_url = "https://github.com/lark-parser/lark/tarball/master",
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
 - Automatic line & column tracking
 - Standard library of terminals (strings, numbers, names, etc.)
 - Import grammars from Nearley.js
 - Extensive test suite
 - And much more!

Since version 1.0, only Python versions 3.6 and up are supported.
''',

    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Text Processing :: General",
        "Topic :: Text Processing :: Linguistic",
        "License :: OSI Approved :: MIT License",
    ],
    entry_points = {
        'pyinstaller40': [
            'hook-dirs = lark.__pyinstaller:get_hook_dirs'
        ]
    },
)

