try:
    import regex as re
except ImportError:
    import re
from setuptools import setup  # , find_packages  # unused

from lark import __version__

#__version__ ,= re.findall('__version__ = "(.*)"', open('lark/__init__.py').read())
with open("README.md") as f:
    README = f.read()

setup(
    name = "lark-parser",
    version = __version__,
    packages = ['lark', 'lark.parsers', 'lark.tools', 'lark.grammars', 'lark.__pyinstaller', 'lark-stubs'],

    requires = [],
    install_requires = [],

    extras_require = {
        "regex": ["regex"],
        "nearley": ["js2py"]
    },

    package_data = {'': ['*.md', '*.lark'], 'lark-stubs': ['*.pyi']},  # Maybe a MANIFEST.ini would be used here

    test_suite = 'tests.__main__',

    # metadata for upload to PyPI
    author = "Erez Shinan",
    author_email = "erezshin@gmail.com",
    description = "a modern parsing library",
    license = "MIT",
    keywords = "Earley LALR parser parsing ast",
    url = "https://github.com/erezsh/lark",
    download_url = "https://github.com/erezsh/lark/tarball/master",
    long_description=README,
    long_description_content_type='text/markdown',
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
    entry_points = {
        'pyinstaller40': [
            'hook-dirs = lark.__pyinstaller:get_hook_dirs'
        ]
    },
)

