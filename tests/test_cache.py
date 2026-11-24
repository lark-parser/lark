from __future__ import absolute_import

import logging
import os
import shutil
import stat
import tempfile
from unittest import TestCase, main, skipIf
from unittest.mock import patch

from lark import Lark, Tree, Transformer, UnexpectedInput
from lark.exceptions import ConfigurationError
from lark.lexer import Lexer, Token
from lark.utils import FS
import lark.lark as lark_module
from lark.reconstruct import Reconstructor
from . import test_reconstructor

from io import BytesIO

try:
    import regex
except ImportError:
    regex = None

class MockFile(BytesIO):
    def close(self):
        pass
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass

class MockFS:
    def __init__(self):
        self.files = {}

    def open(self, name, mode="r", **kwargs):
        if name not in self.files:
            if "r" in mode:
                # If we are reading from a file, it should already exist
                raise FileNotFoundError(name)
            f = self.files[name] = MockFile()
        else:
            f = self.files[name]
            f.seek(0)
        return f

    def exists(self, name):
        return name in self.files


class CustomLexer(Lexer):
    def __init__(self, lexer_conf):
        pass

    def lex(self, data):
        for obj in data:
            yield Token('A', obj)


class InlineTestT(Transformer):
    def add(self, children):
        return sum(children if isinstance(children, list) else children.children)

    def NUM(self, token):
        return int(token)

    def __reduce__(self):
        raise TypeError("This Transformer should not be pickled.")


def append_zero(t):
    return t.update(value=t.value + '0')


class TestCache(TestCase):
    g = '''start: "a"'''


    def setUp(self):
        self.fs = lark_module.FS
        self.mock_fs = MockFS()
        lark_module.FS = self.mock_fs

    def tearDown(self):
        self.mock_fs.files = {}
        lark_module.FS = self.fs

    def test_simple(self):
        fn = "bla"

        Lark(self.g, parser='lalr', cache=fn)
        assert fn in self.mock_fs.files
        parser = Lark(self.g, parser='lalr', cache=fn)
        assert parser.parse('a') == Tree('start', [])

    def test_automatic_naming(self):
        assert len(self.mock_fs.files) == 0
        Lark(self.g, parser='lalr', cache=True)
        assert len(self.mock_fs.files) == 1
        parser = Lark(self.g, parser='lalr', cache=True)
        assert parser.parse('a') == Tree('start', [])

        parser = Lark(self.g + ' "b"', parser='lalr', cache=True)
        assert len(self.mock_fs.files) == 2
        assert parser.parse('ab') == Tree('start', [])

        parser = Lark(self.g, parser='lalr', cache=True)
        assert parser.parse('a') == Tree('start', [])

    def test_custom_lexer(self):

        parser = Lark(self.g, parser='lalr', lexer=CustomLexer, cache=True)
        parser = Lark(self.g, parser='lalr', lexer=CustomLexer, cache=True)
        assert len(self.mock_fs.files) == 1
        assert parser.parse('a') == Tree('start', [])

    def test_options(self):
        # Test options persistence
        Lark(self.g, parser="lalr", debug=True, cache=True)
        parser = Lark(self.g, parser="lalr", debug=True, cache=True)
        assert parser.options.options['debug']

    def test_inline(self):
        # Test inline transformer (tree-less) & lexer_callbacks
        # Note: the Transformer should not be saved to the file,
        #       and is made unpickable to check for that
        g = r"""
        start: add+
        add: NUM "+" NUM
        NUM: /\d+/
        %ignore " "
        """
        text = "1+2 3+4"
        expected = Tree('start', [30, 70])

        parser = Lark(g, parser='lalr', transformer=InlineTestT(), cache=True, lexer_callbacks={'NUM': append_zero})
        res0 = parser.parse(text)
        parser = Lark(g, parser='lalr', transformer=InlineTestT(), cache=True, lexer_callbacks={'NUM': append_zero})
        assert len(self.mock_fs.files) == 1
        res1 = parser.parse(text)
        res2 = InlineTestT().transform(Lark(g, parser="lalr", cache=True, lexer_callbacks={'NUM': append_zero}).parse(text))
        assert res0 == res1 == res2 == expected

    def test_imports(self):
        g = """
        %import .grammars.ab (startab, expr)
        """
        parser = Lark(g, parser='lalr', start='startab', cache=True, source_path=__file__)
        assert len(self.mock_fs.files) == 1
        parser = Lark(g, parser='lalr', start='startab', cache=True, source_path=__file__)
        assert len(self.mock_fs.files) == 1
        res = parser.parse("ab")
        self.assertEqual(res, Tree('startab', [Tree('expr', ['a', 'b'])]))

    @skipIf(regex is None, "'regex' lib not installed")
    def test_recursive_pattern(self):
        g = """
        start: recursive+
        recursive: /\w{3}\d{3}(?R)?/
        """

        assert len(self.mock_fs.files) == 0
        Lark(g, parser="lalr", regex=True, cache=True)
        assert len(self.mock_fs.files) == 1

        with self.assertLogs("lark", level="ERROR") as cm:
            Lark(g, parser='lalr', regex=True, cache=True)
            assert len(self.mock_fs.files) == 1
            # need to add an error log, because 'self.assertNoLogs' was added in Python 3.10
            logging.getLogger('lark').error("dummy message")
        # should only have the dummy log
        self.assertCountEqual(cm.output, ["ERROR:lark:dummy message"])


    def test_error_message(self):
        # Checks that error message generation works
        # This is especially important since sometimes the `str` method fails with
        # the mysterious "<unprintable UnexpectedCharacters object>" or similar
        g = r"""
        start: add+
        add: /\d+/ "+" /\d+/
        %ignore " "
        """
        texts = ("1+", "+1", "", "1 1+1")

        parser1 = Lark(g, parser='lalr', cache=True)
        parser2 = Lark(g, parser='lalr', cache=True)
        assert len(self.mock_fs.files) == 1
        for text in texts:
            with self.assertRaises((UnexpectedInput)) as cm1:
                parser1.parse(text)
            with self.assertRaises((UnexpectedInput)) as cm2:
                parser2.parse(text)
            self.assertEqual(str(cm1.exception), str(cm2.exception))

    def test_cache_grammar(self):
        with self.assertRaises(ConfigurationError):
            Lark(self.g, parser='lalr', cache=False, cache_grammar=True)

        assert len(self.mock_fs.files) == 0
        parser1 = Lark(self.g, parser='lalr', cache=True, cache_grammar=True)
        parser2 = Lark(self.g, parser='lalr', cache=True, cache_grammar=True)
        assert parser2.parse('a') == Tree('start', [])

        # Assert that the cache file was created, and uses a different name than regular cache
        assert len(self.mock_fs.files) == 1
        assert 'cache_grammar' in list(self.mock_fs.files)[0]

        # Assert the cached grammar is equal to the original grammar
        assert parser1.grammar is not parser2.grammar
        assert parser1.grammar.term_defs == parser2.grammar.term_defs
        # Using repr() because RuleOptions doesn't implement __eq__
        assert repr(parser1.grammar.rule_defs) == repr(parser2.grammar.rule_defs)

    def test_reconstruct(self):
        # Test that Reconstructor works with cached parsers (using cache_grammar)
        grammar = """
        start: (rule | NL)*
        rule: WORD ":" NUMBER
        NL: /(\\r?\\n)+\\s*/
        """ + test_reconstructor.common

        code = """
        Elephants: 12
        """

        _parser = Lark(grammar, parser='lalr', maybe_placeholders=False, cache=True, cache_grammar=True)
        assert len(self.mock_fs.files) == 1
        parser = Lark(grammar, parser='lalr', maybe_placeholders=False, cache=True, cache_grammar=True)
        assert _parser.grammar is not parser.grammar
        tree = parser.parse(code)
        new = Reconstructor(parser).reconstruct(tree)
        self.assertEqual(test_reconstructor._remove_ws(code), test_reconstructor._remove_ws(new))


@skipIf(os.name != 'posix', "requires posix file permissions and symlinks")
class TestCacheFile(TestCase):
    # The automatic cache name is derived from the grammar and lives in a shared
    # temporary directory, so another user can predict the path and create it first.

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmpdir, True)
        self.cache_fn = os.path.join(self.tmpdir, 'cache.tmp')
        self.other_fn = os.path.join(self.tmpdir, 'other')
        with open(self.other_fn, 'wb') as f:
            f.write(b'original')

    def test_load_does_not_follow_symlink(self):
        os.symlink(self.other_fn, self.cache_fn)
        with self.assertRaises(PermissionError):
            FS.open(self.cache_fn, 'rb').close()

    def test_save_does_not_follow_symlink(self):
        # The save writes a new file and renames it onto the path, so a symlink is
        # replaced rather than followed.
        os.symlink(self.other_fn, self.cache_fn)
        with FS.open(self.cache_fn, 'wb') as f:
            f.write(b'ours')
        self.assertFalse(os.path.islink(self.cache_fn))
        with open(self.other_fn, 'rb') as f:
            self.assertEqual(f.read(), b'original')

    def test_save_replaces_a_world_writable_cache(self):
        # A cache we own that others can write may have another writer holding a
        # descriptor on it. Rewriting it in place would let that writer overwrite the
        # pickle afterwards, so the save lands on a new 0600 inode instead and leaves
        # the old one alone.
        with open(self.cache_fn, 'wb') as f:
            f.write(b'planted')
        os.chmod(self.cache_fn, 0o666)
        old_ino = os.stat(self.cache_fn).st_ino
        other_writer = open(self.cache_fn, 'rb')
        self.addCleanup(other_writer.close)

        with FS.open(self.cache_fn, 'wb') as f:
            f.write(b'ours')

        st = os.stat(self.cache_fn)
        self.assertNotEqual(st.st_ino, old_ino)
        self.assertEqual(stat.S_IMODE(st.st_mode), 0o600)
        with open(self.cache_fn, 'rb') as f:
            self.assertEqual(f.read(), b'ours')
        self.assertEqual(other_writer.read(), b'planted')   # the old inode is untouched

    def test_lark_warns_on_refused_cache_without_traceback(self):
        # A refused cache path must not break parser construction, and the refusal
        # should surface as a warning, not an exception log.
        os.symlink(self.other_fn, self.cache_fn)
        with self.assertLogs(lark_module.logger, level='WARNING') as cm:
            parser = Lark('start: "a"', parser='lalr', cache=self.cache_fn)
        self.assertEqual([r.levelname for r in cm.records], ['WARNING'] * len(cm.records))
        self.assertTrue(any('Failed to load cache' in r.getMessage() for r in cm.records))
        self.assertEqual(parser.parse('a'), Tree('start', []))
        with open(self.other_fn, 'rb') as f:
            self.assertEqual(f.read(), b'original')

    def test_lark_warns_when_the_cache_cannot_be_saved(self):
        # A directory can't be renamed onto, so the save is refused. Same deal: one
        # warning each for the load and the save, and the parser still works.
        os.mkdir(self.cache_fn)
        with self.assertLogs(lark_module.logger, level='WARNING') as cm:
            parser = Lark('start: "a"', parser='lalr', cache=self.cache_fn)
        self.assertEqual([r.levelname for r in cm.records], ['WARNING'] * len(cm.records))
        self.assertTrue(any('Failed to save cache' in r.getMessage() for r in cm.records))
        self.assertEqual(parser.parse('a'), Tree('start', []))

    def test_save_keeps_cache_private(self):
        with FS.open(self.cache_fn, 'wb') as f:
            f.write(b'data')
        self.assertEqual(stat.S_IMODE(os.stat(self.cache_fn).st_mode) & 0o077, 0)

    def test_load_refuses_group_or_world_writable(self):
        with open(self.cache_fn, 'wb') as f:
            f.write(b'data')
        os.chmod(self.cache_fn, 0o666)
        with self.assertRaises(PermissionError):
            FS.open(self.cache_fn, 'rb').close()

    def test_load_allows_group_readable(self):
        # Only write bits let another user tamper, so a file we own that is merely
        # group/world readable is still fine to load.
        with open(self.cache_fn, 'wb') as f:
            f.write(b'data')
        os.chmod(self.cache_fn, 0o644)
        with FS.open(self.cache_fn, 'rb') as f:
            self.assertEqual(f.read(), b'data')

    def test_save_does_not_write_through_hard_link(self):
        # A hard link to one of our own files has our uid, so an ownership check alone
        # wouldn't catch it. The rename replaces the link instead of writing through it.
        os.link(self.other_fn, self.cache_fn)
        with FS.open(self.cache_fn, 'wb') as f:
            f.write(b'ours')
        self.assertFalse(os.path.samefile(self.cache_fn, self.other_fn))
        with open(self.other_fn, 'rb') as f:
            self.assertEqual(f.read(), b'original')

    def test_load_refuses_hard_link(self):
        os.link(self.other_fn, self.cache_fn)
        with self.assertRaises(PermissionError):
            FS.open(self.cache_fn, 'rb').close()

    def test_refuses_fifo(self):
        # Without O_NONBLOCK the read would block forever waiting for a writer.
        os.mkfifo(self.cache_fn)
        with self.assertRaises(PermissionError):
            FS.open(self.cache_fn, 'rb').close()
        with FS.open(self.cache_fn, 'wb') as f:
            f.write(b'ours')
        self.assertTrue(stat.S_ISREG(os.stat(self.cache_fn).st_mode))

    def test_refuses_directory(self):
        os.mkdir(self.cache_fn)
        with self.assertRaises(PermissionError):
            FS.open(self.cache_fn, 'rb').close()
        with self.assertRaises(PermissionError):
            with FS.open(self.cache_fn, 'wb') as f:
                f.write(b'ours')
        self.assertTrue(os.path.isdir(self.cache_fn))
        # the file the save was building must not be left behind
        self.assertEqual(sorted(os.listdir(self.tmpdir)), ['cache.tmp', 'other'])

    def test_unguarded_cache(self):
        # The checks are on by default. unguarded_cache=True skips them, and since it
        # isn't part of the cache key, it loads the file that was already there.
        g = 'start: "a"'
        Lark(g, parser='lalr', cache=self.cache_fn)
        os.chmod(self.cache_fn, 0o666)
        with patch.object(lark_module, 'load_grammar', wraps=lark_module.load_grammar) as load_grammar:
            parser = Lark(g, parser='lalr', cache=self.cache_fn, unguarded_cache=True)
            self.assertEqual(load_grammar.call_count, 0)    # loaded from the cache
            self.assertEqual(parser.parse('a'), Tree('start', []))

            with self.assertLogs(lark_module.logger, level='WARNING') as cm:
                parser = Lark(g, parser='lalr', cache=self.cache_fn)
            self.assertEqual(load_grammar.call_count, 1)    # refused, so rebuilt
            self.assertTrue(any('Failed to load cache' in r.getMessage() for r in cm.records))
            self.assertEqual(parser.parse('a'), Tree('start', []))

    def test_unguarded_open_skips_checks(self):
        with open(self.cache_fn, 'wb') as f:
            f.write(b'data')
        os.chmod(self.cache_fn, 0o666)
        with FS.open(self.cache_fn, 'rb', unguarded=True) as f:
            self.assertEqual(f.read(), b'data')


class TestCacheFilePortable(TestCase):
    # Runs everywhere, including Windows, where the posix-only checks above are skipped:
    # FS.open must still round-trip a normal read/write.

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmpdir, True)
        self.cache_fn = os.path.join(self.tmpdir, 'cache.tmp')

    def test_open_roundtrip(self):
        with FS.open(self.cache_fn, 'wb') as f:
            f.write(b'roundtrip')
        with FS.open(self.cache_fn, 'rb') as f:
            self.assertEqual(f.read(), b'roundtrip')

    def test_open_replaces_existing_on_write(self):
        with FS.open(self.cache_fn, 'wb') as f:
            f.write(b'longer original content')
        with FS.open(self.cache_fn, 'wb') as f:
            f.write(b'short')
        with FS.open(self.cache_fn, 'rb') as f:
            self.assertEqual(f.read(), b'short')
        # the file the save was built in is renamed into place, not left next to it
        self.assertEqual(os.listdir(self.tmpdir), ['cache.tmp'])

    def test_write_leaves_nothing_behind_when_it_fails(self):
        class Boom(Exception):
            pass
        with self.assertRaises(Boom):
            with FS.open(self.cache_fn, 'wb') as f:
                f.write(b'half')
                raise Boom()
        self.assertEqual(os.listdir(self.tmpdir), [])

    def test_unguarded_cache_roundtrip(self):
        g = 'start: "a"'
        Lark(g, parser='lalr', cache=self.cache_fn, unguarded_cache=True)
        with patch.object(lark_module, 'load_grammar', wraps=lark_module.load_grammar) as load_grammar:
            parser = Lark(g, parser='lalr', cache=self.cache_fn, unguarded_cache=True)
        self.assertEqual(load_grammar.call_count, 0)
        self.assertEqual(parser.parse('a'), Tree('start', []))

    def test_cache_true_miss_then_hit(self):
        # cache=True uses a file in the temp dir; point that at our own directory.
        g = 'start: "a"'
        with patch('tempfile.gettempdir', return_value=self.tmpdir), \
             patch.object(lark_module, 'load_grammar', wraps=lark_module.load_grammar) as load_grammar:
            Lark(g, parser='lalr', cache=True)
            self.assertEqual(load_grammar.call_count, 1)    # miss: built and saved
            [cache_name] = os.listdir(self.tmpdir)
            self.assertTrue(cache_name.startswith('.lark_cache_'))
            parser = Lark(g, parser='lalr', cache=True)
            self.assertEqual(load_grammar.call_count, 1)    # hit: loaded from the cache
        self.assertEqual(parser.parse('a'), Tree('start', []))


if __name__ == '__main__':
    main()
