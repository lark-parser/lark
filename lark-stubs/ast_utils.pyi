import types
from typing import Optional

from .visitors import Transformer

class Ast(object):
    pass

class AsList(object):
    pass


def create_transformer(
        ast_module: types.ModuleType,
        transformer: Optional[Transformer]=None
) -> Transformer:
    ...