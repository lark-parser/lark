import logging
from contextlib import contextmanager
from lark import Lark, logger
from unittest import TestCase, main

try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO

@contextmanager
def capture_log():
    stream = StringIO()
    orig_handler = logger.handlers[0]
    del logger.handlers[:]
    logger.addHandler(logging.StreamHandler(stream))
    yield stream
    del logger.handlers[:]
    logger.addHandler(orig_handler)

class Testlogger(TestCase):

    def test_debug(self):
        logger.setLevel(logging.DEBUG)
        collision_grammar = '''
        start: as as
        as: a*
        a: "a"
        '''
        with capture_log() as log:
            Lark(collision_grammar, parser='lalr', debug=True)

        log = log.getvalue()
        # since there are conflicts about A
        # symbol A should appear in the log message for hint
        self.assertIn("A", log)

    def test_non_debug(self):
        logger.setLevel(logging.DEBUG)
        collision_grammar = '''
        start: as as
        as: a*
        a: "a"
        '''
        with capture_log() as log:
            Lark(collision_grammar, parser='lalr', debug=False)
        log = log.getvalue()
        # no log messge
        self.assertEqual(len(log), 0)

    def test_loglevel_higher(self):
        logger.setLevel(logging.ERROR)
        collision_grammar = '''
        start: as as
        as: a*
        a: "a"
        '''
        with capture_log() as log:
            Lark(collision_grammar, parser='lalr', debug=True)
        log = log.getvalue()
        # no log messge
        self.assertEqual(len(log), 0)

if __name__ == '__main__':
    main()
