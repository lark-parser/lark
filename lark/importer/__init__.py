import sys
import filefinder2

from .finder import LarkFinder
from .loader import LarkLoader


class LarkImporter:
    """
    Context manager for activating/deactivating *.lark imports
    """
    def __init__(self, extensions=None):
        self.extensions = extensions or ['.lark']
        pass

    def __enter__(self):
        # Resetting sys.path_importer_cache to get rid of previous importers
        sys.path_importer_cache.clear()
        # TODO : investigate BUG here, sometime debugger (pycharm) needs to have a break here to actually drop his importer_cache
        # This can lead to finder not being called if Python's FileFinder is already cached (for current dir for example)

        # we hook the grammar customized loader
        self._lfh = LarkFinder.path_hook((LarkLoader, self.extensions), )

        if self._lfh not in sys.path_hooks:
            sys.path_hooks.insert(filefinder2.get_filefinder_index_in_path_hooks(), self._lfh)

    def __exit__(self, exc_type, exc_val, exc_tb):
        # CAREFUL : Even though we remove the path from sys.path,
        # initialized finders will remain in sys.path_importer_cache

        # removing path_hook
        sys.path_hooks.pop(sys.path_hooks.index(self._lfh))

        # Resetting sys.path_importer_cache to get rid of previous cached importers
        sys.path_importer_cache.clear()

