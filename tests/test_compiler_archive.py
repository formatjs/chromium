import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tools.ci import compiler_archive as compiler


class CompilerArchiveTest(unittest.TestCase):
    def test_corrupt_cached_archive_rejected_without_fetch_or_configuration(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / compiler.NAME
            with mock.patch.object(compiler, 'api_request', side_effect=AssertionError('unexpected fetch')):
                for size in [7, compiler.SIZE]:
                    with self.subTest(size=size):
                        with archive.open('wb') as output:
                            output.truncate(size)
                        with self.assertRaisesRegex(ValueError, 'SHA256/size mismatch'):
                            compiler.ensure_archive(archive)

    def test_explicit_archive_changes_only_selected_host_index_and_build_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / 'source'
            (source / 'build').mkdir(parents=True)
            (source / 'MODULE.bazel').write_text('module(name="test")\n')
            (source / 'BUILD.bazel').write_text('exports_files([])\n')
            code = source / 'browser.cc'
            code.write_text('int browser() { return 42; }\n')
            original = {'linux-amd64-musl': {'url': 'https://example.com/baseline.tar.zst',
                                            'sha256': compiler.BASELINE_SHA256},
                        'linux-arm64-musl': {'url': 'https://example.com/arm.tar.zst', 'sha256': '1' * 64},
                        'windows-amd64-msvc': {'url': 'https://example.com/msvc.tar.zst', 'sha256': '2' * 64}}
            index = {'default_prebuilt_llvm_version': '23.1.2',
                     'latest_by_llvm_version': {'23.1.2': 'original'}, 'releases': {'original': original}}
            template = source / 'build/llvm-compiler-base-index.json'
            template.write_text(json.dumps(index))
            archive = Path(temporary) / compiler.NAME
            with mock.patch.object(compiler, 'verify_archive', return_value=archive):
                report = compiler.configure_compiler(source, archive)
                with self.assertRaisesRegex(ValueError, 'already selects'):
                    compiler.configure_compiler(source, archive)
            selected = json.loads((source / '_cold_compiler_index.json').read_text())
            self.assertEqual(selected['releases']['original'], original)
            self.assertEqual(json.loads(template.read_text()), index)
            replacement = selected['releases'][selected['latest_by_llvm_version']['23.1.2']]
            self.assertEqual(replacement['linux-amd64-musl'], {'url': archive.as_uri(), 'sha256': compiler.SHA256})
            for host in ['linux-arm64-musl', 'windows-amd64-msvc']:
                self.assertEqual(replacement[host], original[host])
            self.assertEqual(code.read_text(), 'int browser() { return 42; }\n')
            self.assertEqual(report['configured_module_sha256'], compiler.digest(source / 'MODULE.bazel'))
            self.assertIn('cold_llvm_prebuilt.index', (source / 'MODULE.bazel').read_text())

    def test_actual_compiler_binary_must_match_pin(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            driver = root / ('external/llvm++llvm_toolchain_minimal+'
                             'llvm-toolchain-minimal-linux-amd64/bin/clang++')
            driver.parent.mkdir(parents=True)
            driver.write_bytes(b'unexpected compiler')
            with self.assertRaisesRegex(ValueError, 'pinned trained compiler binary'):
                compiler.verify_compiler(root)


if __name__ == '__main__':
    unittest.main()
