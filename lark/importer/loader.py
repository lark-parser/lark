"""
A module to load lark grammar files
"""

# We need to be extra careful with python versions
# Ref : https://docs.python.org/dev/library/importlib.html#importlib.import_module

import filefinder2.machinery

import lark  # just to make sure lark is loaded and our generated python code can be interpreted
from._utils import _verbose_message


class LarkLoader(filefinder2.machinery.SourceFileLoader):

    # CAREFUL : on some python versions, removing get_code breaks the loader.
    def get_code(self, fullname):
        source = self.get_source(fullname)
        _verbose_message('importing code for "{0}"'.format(fullname))
        try:
            code = self.source_to_code(source, self.get_filename(fullname))
            return code
        except TypeError:
            raise

    def get_source(self, name):
        """Implementing actual python code from file content"""
        path = self.get_filename(name)

        # Returns decoded string from source file
        larkstr = super(LarkLoader, self).get_source(name)
        larkstr = "from lark import Lark; parser = Lark(\"\"\"{larkstr}\"\"\", parser='lalr')""".format(**locals())

        return larkstr
