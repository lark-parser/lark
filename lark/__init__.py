from .tree import Tree
from .visitors import Transformer, Visitor, v_args, Discard
from .visitors import InlineTransformer, inline_args   # XXX Deprecated
from .exceptions import (ParseError, LexError, GrammarError, UnexpectedToken,
                         UnexpectedInput, UnexpectedCharacters, LarkError)
from .lexer import Token
from .lark import Lark

cnffile = open('larkc.txt')
if cnffile.read() == '1':
  hook = open('lark-hook.py','w')
  hook.write('from PyInstaller.utils.hooks import collect_data_files;datas = collect_data_files('lark')')

__version__ = "0.8.5"
