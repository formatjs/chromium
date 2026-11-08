"""Captured header changes must stop the PCH handoff."""

import unittest

from tools.ci.compile.validate_pch import validate


class PchClosureTest(unittest.TestCase):
    def test_source_and_generated_paths_match(self):
        validate('out.pch: external/repo/a.h \\\n bazel-out/k8-fastbuild/bin/external/repo/generated.h \\\n external/llvm++toolchain/include/stddef.h\n', ['repo/a.h', 'repo/generated.h'])

    def test_changed_imports_fail(self):
        for dependency in ['out: external/repo/a.h external/repo/extra.h', 'out: external/repo/replacement.h', 'out: ']:
            with self.subTest(dependency=dependency), self.assertRaisesRegex(ValueError, 'closure changed'):
                validate(dependency, ['repo/a.h'])

    def test_unsafe_or_unsupported_paths_fail(self):
        for path in ['/usr/include/a.h', 'external/repo/../a.h', 'bazel-out/k8-fastbuild/genfiles/a.h', 'external/repo/a\\ b.h', 'external/repo/$(file).h']:
            with self.subTest(path=path), self.assertRaises(ValueError):
                validate('out: ' + path, ['repo/a.h'])


if __name__ == '__main__':
    unittest.main()
