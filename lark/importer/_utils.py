from __future__ import absolute_import, print_function

import sys


def _verbose_message(message, *args, **kwargs):
    """Print the message to stderr if -v/PYTHONVERBOSE is turned on."""
    verbosity = kwargs.pop('verbosity', 1)
    if sys.flags.verbose >= verbosity:
        if not message.startswith(('#', 'import ')):
            message = '# ' + message
        print(message.format(*args), file=sys.stderr)


try:
    ImportError('msg', name='name', path='path')
except TypeError:
    class _ImportError(ImportError):
        def __init__(self, *args, **kwargs):
            self.name = kwargs.pop('name', None)
            self.path = kwargs.pop('path', None)
            super(_ImportError, self).__init__(*args, **kwargs)
else:
    _ImportError = ImportError
