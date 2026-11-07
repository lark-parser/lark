from __future__ import absolute_import

import logging
import os
import subprocess
import sys
from tempfile import TemporaryDirectory
from unittest import TestCase, main, skipIf
from unittest.mock import patch

from lark import Lark, Tree, Transformer, UnexpectedInput
from lark.exceptions import ConfigurationError
from lark.lexer import Lexer, Token
import lark.lark as lark_module
from lark.reconstruct import Reconstructor
from lark.parsers.earley_forest import TreeForestTransformer
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

    def test_earley_cache(self):
        grammar = 'start: item*\nitem: "a" ["b"]'
        for lexer in ('basic', 'dynamic', 'dynamic_complete'):
            for cache in (True, 'earley-cache'):
                with self.subTest(lexer=lexer, cache=cache):
                    self.mock_fs.files.clear()
                    original = Lark(grammar, lexer=lexer, cache=cache)
                    expected = original.parse('aaba')
                    with patch('lark.lark.load_grammar', side_effect=AssertionError('grammar reloaded')) as compile_grammar, \
                            patch('lark.parsers.earley.GrammarAnalyzer', side_effect=AssertionError('analysis repeated')) as analyze:
                        restored = Lark(grammar, lexer=lexer, cache=cache)
                        self.assertEqual(restored.parse('aaba'), expected)
                        self.assertEqual(restored.parse(''), original.parse(''))
                        compile_grammar.assert_not_called()
                        analyze.assert_not_called()
                    self.assertEqual(len(self.mock_fs.files), 1)

    def test_earley_save_load(self):
        grammar = '''
            start: left | right
            left.1: word+
            right.2: word+
            word: "a" ["b"]
            empty:
            %ignore " "
        '''
        for lexer in ('basic', 'dynamic', 'dynamic_complete'):
            for ambiguity in ('resolve', 'explicit', 'forest'):
                for priority in ('normal', 'invert', None):
                    for ordered_sets in (True, False):
                        with self.subTest(lexer=lexer, ambiguity=ambiguity, priority=priority, ordered_sets=ordered_sets):
                            original = Lark(grammar, lexer=lexer, ambiguity=ambiguity,
                                            priority=priority, ordered_sets=ordered_sets,
                                            start=['start', 'empty'], keep_all_tokens=True)
                            data = BytesIO()
                            original.save(data)
                            data.seek(0)
                            with patch('lark.parsers.earley.GrammarAnalyzer', side_effect=AssertionError('analysis repeated')) as analyze:
                                restored = Lark.load(data)
                                analyze.assert_not_called()
                            for text, start in [('ab a', 'start'), ('', 'empty')]:
                                expected = original.parse(text, start=start)
                                actual = restored.parse(text, start=start)
                                if ambiguity == 'forest':
                                    expected = TreeForestTransformer(resolve_ambiguity=False).transform(expected)
                                    actual = TreeForestTransformer(resolve_ambiguity=False).transform(actual)
                                self.assertEqual(actual, expected)

    def test_earley_dynamic_complete(self):
        grammar = 'start: A A\nA: /a+/'
        for cache in (False, True):
            with self.subTest(cache=cache):
                original = Lark(grammar, lexer='dynamic_complete', ambiguity='explicit', cache=cache)
                expected = original.parse('aaa')
                self.assertEqual(expected.data, '_ambig')
                self.assertEqual(len(expected.children), 2)
                data = BytesIO()
                original.save(data)
                data.seek(0)
                self.assertEqual(Lark.load(data).parse('aaa'), expected)

    def test_earley_cache_rebinds_tree_options(self):
        class CustomTree(Tree):
            def __reduce__(self):
                raise TypeError('Tree instances must not be cached')

        grammar = 'start: WORD+\nWORD: /[a-z]+/\n%ignore /\\s+/'
        for lexer in ('basic', 'dynamic', 'dynamic_complete'):
            with self.subTest(lexer=lexer):
                self.mock_fs.files.clear()
                Lark(grammar, lexer=lexer, cache=True, tree_class=CustomTree,
                     propagate_positions=True).parse('before')
                with patch('lark.parsers.earley.GrammarAnalyzer', side_effect=AssertionError('analysis repeated')) as analyze:
                    parser = Lark(grammar, lexer=lexer, cache=True,
                                  tree_class=CustomTree, propagate_positions=True)
                    tree = parser.parse('one\n two')
                    self.assertIsInstance(tree, CustomTree)
                    self.assertEqual((tree.meta.line, tree.meta.column, tree.meta.end_line,
                                      tree.meta.end_column, tree.meta.start_pos, tree.meta.end_pos),
                                     (1, 1, 2, 5, 0, 8))
                    analyze.assert_not_called()

    def test_earley_cache_rebinds_lexer_callbacks_and_postlex(self):
        class AddSuffix:
            always_accept = ()

            def __init__(self, suffix):
                self.suffix = suffix

            def process(self, stream):
                for token in stream:
                    yield token.update(value=token.value + self.suffix)

            def __reduce__(self):
                raise TypeError('Postlex must be supplied again on cache load')

        grammar = 'start: NUM\nNUM: /[0-9]+/'
        Lark(grammar, lexer='basic', cache=True, postlex=AddSuffix('1'))
        with patch('lark.parsers.earley.GrammarAnalyzer', side_effect=AssertionError('analysis repeated')) as analyze:
            parser = Lark(grammar, lexer='basic', cache=True, postlex=AddSuffix('2'),
                          lexer_callbacks={'NUM': append_zero})
            self.assertEqual(parser.parse('3').children, ['302'])
            analyze.assert_not_called()

    def test_earley_cache_lexer_selection_with_postlex(self):
        class IdentityPostLex:
            always_accept = ()

            def process(self, stream):
                return stream

        from lark.parsers.earley import GrammarAnalyzer

        grammar = 'start: A | B\nA: "a"\nB: "a"'
        for cache in (True, 'earley-cache'):
            for lexer_options in ({}, {'lexer': 'auto'}, {'lexer': 'basic'}):
                for first_postlex in (None, IdentityPostLex()):
                    with self.subTest(cache=cache, lexer=lexer_options, postlex=first_postlex):
                        self.mock_fs.files.clear()
                        second_postlex = IdentityPostLex() if first_postlex is None else None
                        Lark(grammar, ambiguity='explicit', cache=cache,
                             postlex=first_postlex, **lexer_options)
                        expected = Lark(grammar, ambiguity='explicit',
                                        postlex=second_postlex, **lexer_options)
                        with patch('lark.lark.load_grammar', wraps=lark_module.load_grammar) as compile_grammar, \
                                patch('lark.parsers.earley.GrammarAnalyzer', wraps=GrammarAnalyzer) as analyze, \
                                patch.object(lark_module.logger, 'exception') as log_error:
                            restored = Lark(grammar, ambiguity='explicit', cache=cache,
                                            postlex=second_postlex, **lexer_options)
                            if lexer_options.get('lexer') == 'basic':
                                compile_grammar.assert_not_called()
                                analyze.assert_not_called()
                            else:
                                compile_grammar.assert_called_once()
                                analyze.assert_called_once()
                            log_error.assert_not_called()
                        self.assertEqual(restored.options.lexer, expected.options.lexer)
                        self.assertEqual(restored.parse('a'), expected.parse('a'))
                        with patch('lark.parsers.earley.GrammarAnalyzer', side_effect=AssertionError('analysis repeated')) as analyze:
                            cached = Lark(grammar, ambiguity='explicit', cache=cache,
                                          postlex=second_postlex, **lexer_options)
                            self.assertEqual(cached.parse('a'), expected.parse('a'))
                            analyze.assert_not_called()

    @skipIf(regex is None, "'regex' lib not installed")
    def test_earley_cache_regex_and_bytes(self):
        for lexer in ('basic', 'dynamic', 'dynamic_complete'):
            for use_bytes in (False, True):
                with self.subTest(lexer=lexer, use_bytes=use_bytes):
                    self.mock_fs.files.clear()
                    grammar = r'start: /(?V1)[a-z&&[^b]]+/'
                    options = dict(lexer=lexer, use_bytes=use_bytes, regex=True, cache=True)
                    original = Lark(grammar, **options)
                    text = b'ac' if use_bytes else 'ac'
                    expected = original.parse(text)
                    with patch('lark.parsers.earley.GrammarAnalyzer', side_effect=AssertionError('analysis repeated')) as analyze:
                        restored = Lark(grammar, **options)
                        self.assertEqual(restored.parse(text), expected)
                        analyze.assert_not_called()

    def test_earley_cache_invalidation(self):
        for lexer in ('basic', 'dynamic', 'dynamic_complete'):
            with self.subTest(lexer=lexer):
                self.mock_fs.files.clear()
                Lark('start: "a"', lexer=lexer, cache='cache')
                parser = Lark('start: "b"', lexer=lexer, cache='cache')
                self.assertEqual(parser.parse('b'), Tree('start', []))
                with self.assertRaises(UnexpectedInput):
                    parser.parse('a')
                parser = Lark('start: "b"', lexer=lexer, cache='cache', keep_all_tokens=True)
                self.assertEqual(parser.parse('b').children, ['b'])

    def test_earley_cache_errors_and_reconstruction(self):
        grammar = 'start: "a" "b"\n%ignore " "'
        for lexer in ('basic', 'dynamic', 'dynamic_complete'):
            with self.subTest(lexer=lexer):
                self.mock_fs.files.clear()
                options = dict(lexer=lexer, cache=True, cache_grammar=True, maybe_placeholders=False)
                original = Lark(grammar, **options)
                restored = Lark(grammar, **options)
                self.assertEqual(Reconstructor(restored).reconstruct(restored.parse('a b')),
                                 Reconstructor(original).reconstruct(original.parse('a b')))
                for text in ('a', 'c'):
                    with self.assertRaises(UnexpectedInput) as first:
                        original.parse(text)
                    with self.assertRaises(UnexpectedInput) as second:
                        restored.parse(text)
                    self.assertIs(type(second.exception), type(first.exception))
                    self.assertEqual(str(second.exception), str(first.exception))

    def test_earley_save_load_across_processes(self):
        grammar = 'start: a+\na: "a" [a]'
        script = '''
import sys
from lark import Lark
from unittest.mock import patch
filename, mode, lexer, grammar = sys.argv[1:]
if mode == 'save':
    parser = Lark(grammar, lexer=lexer, ambiguity='explicit')
    with open(filename, 'wb') as stream:
        parser.save(stream)
else:
    with patch('lark.parsers.earley.GrammarAnalyzer', side_effect=AssertionError('analysis repeated')):
        with open(filename, 'rb') as stream:
            parser = Lark.load(stream)
print(parser.parse('aaa').pretty())
'''
        with TemporaryDirectory() as directory:
            for lexer in ('basic', 'dynamic', 'dynamic_complete'):
                with self.subTest(lexer=lexer):
                    outputs = []
                    for mode, seed in [('save', '1'), ('load', '2')]:
                        env = dict(os.environ, PYTHONHASHSEED=seed)
                        outputs.append(subprocess.check_output(
                            [sys.executable, '-c', script, os.path.join(directory, 'parser'), mode, lexer, grammar],
                            env=env, universal_newlines=True))
                    self.assertEqual(*outputs)

    def test_earley_cache_custom_lexer(self):
        grammar = 'start: A+\n%declare A'
        Lark(grammar, lexer=CustomLexer, cache=True)
        with patch('lark.parsers.earley.GrammarAnalyzer', side_effect=AssertionError('analysis repeated')) as analyze:
            parser = Lark(grammar, lexer=CustomLexer, cache=True)
            self.assertEqual([token.value for token in parser.parse([1, 2]).children], [1, 2])
            analyze.assert_not_called()

    def test_earley_cache_terminal_priority(self):
        grammar = 'start: A | B\nA.1: "a"\nB.2: "a"'
        for lexer in ('basic', 'dynamic', 'dynamic_complete'):
            with self.subTest(lexer=lexer):
                self.mock_fs.files.clear()
                Lark(grammar, lexer=lexer, cache=True)
                parser = Lark(grammar, lexer=lexer, cache=True)
                self.assertEqual(parser.parse('a').children[0].type, 'B')

    def test_earley_cache_imports_and_corrupt_data(self):
        grammar = '%import .grammars.ab (startab, expr)'
        options = dict(start='startab', cache='cache', source_path=__file__)
        original = Lark(grammar, **options)
        with patch('lark.lark.load_grammar', side_effect=AssertionError('grammar reloaded')) as compile_grammar:
            restored = Lark(grammar, **options)
            self.assertEqual(restored.parse('ab'), original.parse('ab'))
            compile_grammar.assert_not_called()
        self.mock_fs.files['cache'] = MockFile(b'invalid cache')
        with self.assertLogs('lark', level='ERROR'):
            rebuilt = Lark(grammar, **options)
        self.assertEqual(rebuilt.parse('ab'), original.parse('ab'))

    def test_unsupported_parser_cache(self):
        for parser in ('cyk', None):
            with self.subTest(parser=parser):
                with self.assertRaises(ConfigurationError):
                    Lark(self.g, parser=parser, cache=True)
                with self.assertRaises(NotImplementedError):
                    Lark(self.g, parser=parser, lexer='basic').save(BytesIO())

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
        g = r"""
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


if __name__ == '__main__':
    main()
