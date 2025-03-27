def configurations(cases):
    def decorator(f):
        def inner(self):
            for case in cases:
                f.__name__ += f".case({case})"
                f.__qualname__ += f".case({case})"
                f(self, case)
        inner.__name__ = f.__name__
        inner.__qualname__ = f.__qualname__
        return inner
    return decorator

import_test = configurations(("new", "legacy"))
