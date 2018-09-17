###{standalone
try:
    from debug_tools import getLogger

except ( ImportError, ValueError ):   # Python 3
    # getLogger is a function, but it returns a class object
    class getLogger(object):
        name = ""
        level = 0
        parent = None
        propagate = False
        handlers = None
        disabled = False
        def __call__(*args, **kwargs): pass
        def __init__(self, *args, **kwargs): pass
        def setLevel(self, level): pass
        def debug(self, msg, *args, **kwargs): pass
        def info(self, msg, *args, **kwargs): pass
        def warning(self, msg, *args, **kwargs): pass
        def warn(self, msg, *args, **kwargs): pass
        def error(self, msg, *args, **kwargs): pass
        def exception(self, msg, *args, **kwargs): pass
        def critical(self, msg, *args, **kwargs): pass
        def log(self, level, msg, *args, **kwargs): pass
        def findCaller(self, stack_info=False): pass
        def makeRecord(self, name, level, fn, lno, msg, args, exc_info, func=None, extra=None, sinfo=None): pass
        def handle(self, record): pass
        def addHandler(self, hdlr): pass
        def removeHandler(self, hdlr): pass
        def hasHandlers(self): pass
        def callHandlers(self, record): pass
        def getEffectiveLevel(self): pass
        def isEnabledFor(self, level): pass
        def getChild(self, suffix): pass

log = getLogger('lark', force=1)
###}
