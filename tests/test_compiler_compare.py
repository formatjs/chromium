import copy
import hashlib
import tempfile
from pathlib import Path
import unittest

from tools.ci.compile import compiler_compare as comparison


class CompilerComparisonTest(unittest.TestCase):
    def test_only_linux_host_compiler_archive_changes(self):
        archive = Path('/tmp/candidate.tar.zst')
        index = {'latest_by_llvm_version': {'23.1.2': 'release'}, 'releases': {'release': {
            'linux-amd64-musl': {'url': 'https://upstream.example/llvm.tar.zst',
                                 'sha256': comparison.BASELINE_SHA256},
            'darwin-arm64': {'url': 'https://upstream.example/mac.tar.zst', 'sha256': '2' * 64},
        }}}
        original = copy.deepcopy(index)
        changed = comparison.replacement_index(index, archive, '1' * 64)
        self.assertEqual(index, original)
        self.assertEqual(changed['releases']['release']['darwin-arm64'],
                         original['releases']['release']['darwin-arm64'])
        self.assertEqual(changed['releases']['release']['linux-amd64-musl'],
                         {'url': archive.as_uri(), 'sha256': '1' * 64})
        index['releases']['release']['linux-amd64-musl']['sha256'] = '3' * 64
        with self.assertRaisesRegex(ValueError, 'baseline compiler'):
            comparison.replacement_index(index, archive, '1' * 64)

    def test_replacement_compilers_require_matching_archive_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / 'candidate.tar.zst'
            archive.write_bytes(b'compiler')
            digest = hashlib.sha256(b'compiler').hexdigest()
            self.assertEqual(comparison.verified_archive(archive, digest), archive)
            archive.write_bytes(b'tampered')
            with self.assertRaisesRegex(ValueError, 'verified'):
                comparison.verified_archive(archive, digest)

    def test_deletion_inventory_rejects_escaping_foreign_and_duplicate_outputs(self):
        root = Path('/tmp/probe/execroot/chromium')
        outputs = ['bazel-out/k8-fastbuild/bin/tools/ci/compile/compiler_compare/_objs/base/'
                   + str(number) + '.o' for number in range(len(comparison.SOURCES))]
        self.assertEqual(comparison.object_paths([outputs], root), [root / item for item in outputs])
        for bad in ['/etc/foreign.o', 'bazel-out/../outside.o',
                    'bazel-out/k8-fastbuild/bin/other/_objs/base/0.o', outputs[1]]:
            with self.subTest(path=bad), self.assertRaises(ValueError):
                comparison.object_paths([[bad, *outputs[1:]]], root)

    def test_command_comparison_expands_parameters_and_rejects_missing_sources(self):
        direct = {'actions': [{'mnemonic': 'CppCompile', 'arguments': [
            'external/llvm+/toolchain/stage0_linux_x86_64/bin/clang++', '-O3', '-c', source],
            'environmentVariables': [{'key': 'LANG', 'value': 'C'}]}
            for source in comparison.SOURCES]}
        response = copy.deepcopy(direct)
        for action in response['actions']:
            action['paramFiles'] = [{'execPath': 'compiler.params', 'arguments': action['arguments'][1:]}]
            action['arguments'] = [action['arguments'][0], '@compiler.params']
        self.assertEqual(comparison.compiler_commands(direct), comparison.compiler_commands(response))
        response['actions'][0]['paramFiles'][0]['arguments'][0] = '-O2'
        self.assertNotEqual(comparison.compiler_commands(direct), comparison.compiler_commands(response))
        response['actions'].pop()
        with self.assertRaisesRegex(ValueError, 'commands missing'):
            comparison.compiler_commands(response)


if __name__ == '__main__':
    unittest.main()
