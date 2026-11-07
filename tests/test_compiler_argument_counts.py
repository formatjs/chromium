import unittest

from tools.ci.compile.includes import compiler_search_count, compiler_search_paths


class CompilerArgumentCountsTest(unittest.TestCase):
    def test_hidden_response_files_cannot_masquerade_as_empty_search_lists(self):
        for arguments in [[], ['clang', '@compile.params']]:
            with self.subTest(arguments=arguments), self.assertRaisesRegex(ValueError, 'Expanded compiler arguments'):
                compiler_search_count(arguments)
        self.assertEqual(compiler_search_count(
            ['clang', '-isystem', 'headers', '-Igenerated', '-iquote', 'sources', '-c', 'test.cc']), 3)

    def test_search_paths_preserve_order_kind_and_spaces(self):
        self.assertEqual(compiler_search_paths([
            'clang', '-include', 'forced.h', '-isystem', 'system headers',
            '-Igenerated', '-iquotequotes', '-I', 'source headers', '-c', 'test.cc',
        ]), [
            {'flag': '-isystem', 'path': 'system headers'},
            {'flag': '-I', 'path': 'generated'},
            {'flag': '-iquote', 'path': 'quotes'},
            {'flag': '-I', 'path': 'source headers'},
        ])
        with self.assertRaisesRegex(ValueError, 'Compiler search path missing'):
            compiler_search_paths(['clang', '-I'])


if __name__ == '__main__':
    unittest.main()
