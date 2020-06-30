import logging
from contextlib import contextmanager
from lark import Lark, LOGGER
from unittest import TestCase, main

try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO

@contextmanager
def capture_log():
    stream = StringIO()
    orig_handler = LOGGER.handlers[0]
    del LOGGER.handlers[:]
    LOGGER.addHandler(logging.StreamHandler(stream))
    yield stream
    del LOGGER.handlers[:]
    LOGGER.addHandler(orig_handler)

class TestLogger(TestCase):

    def test_debug(self):
        LOGGER.setLevel(logging.DEBUG)
        collision_grammar = '''
        start: as as
        as: a*
        a: "a"
        '''
        with capture_log() as log:
            Lark(collision_grammar, parser='lalr', debug=True)

        log = log.getvalue()
        self.assertIn("Shift/Reduce conflict for terminal", log)
        self.assertIn("A: (resolving as shift)", log)
        self.assertIn("Shift/Reduce conflict for terminal A: (resolving as shift)", log)

    def test_non_debug(self):
        LOGGER.setLevel(logging.DEBUG)
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
        LOGGER.setLevel(logging.ERROR)
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
