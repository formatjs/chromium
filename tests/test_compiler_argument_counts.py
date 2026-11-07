import unittest

from tools.ci.compile.includes import compiler_search_count


class CompilerArgumentCountsTest(unittest.TestCase):
    def test_hidden_response_files_cannot_masquerade_as_empty_search_lists(self):
        for arguments in [[], ['clang', '@compile.params']]:
            with self.subTest(arguments=arguments), self.assertRaisesRegex(ValueError, 'Expanded compiler arguments'):
                compiler_search_count(arguments)
        self.assertEqual(compiler_search_count(
            ['clang', '-isystem', 'headers', '-Igenerated', '-iquote', 'sources', '-c', 'test.cc']), 3)


if __name__ == '__main__':
    unittest.main()
