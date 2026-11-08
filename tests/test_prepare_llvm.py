import json
from pathlib import Path
import tempfile
import unittest

from tools.ci import prepare_llvm


class CompilerPreparationTest(unittest.TestCase):
    def test_release_settings_survive_removing_upstream_services(self):
        release = '\n'.join([
            'common:release -c opt',
            'common:release --features=thin_lto',
            'common:release --features=no_exceptions',
            'common:release --extra_execution_platforms=@rbe_platform//:rbe_linux_x86_64_musl',
            'common --per_file_copt=external/.*llvm-project.*@-Xclang=-Wno-thread-safety-analysis',
        ]) + '\n'
        upstream = release + '\n'.join([
            'common --remote_header=x-buildbuddy-api-key=upstream-test-key',
            'common --bes_header=x-buildbuddy-api-key=upstream-test-key',
            'common --remote_executor=grpcs://upstream.example',
            'common --remote_cache=grpcs://upstream.example',
            'common --bes_backend=grpcs://upstream.example',
            'common --experimental_remote_downloader=grpcs://upstream.example',
            'try-import %workspace%/.bazelrc.user',
        ])
        self.assertEqual(prepare_llvm.preparation_rc(upstream), release)

    def test_unexpected_import_requires_review(self):
        for directive in ['import /etc/custom.bazelrc', 'try-import %workspace%/other.bazelrc']:
            with self.subTest(directive=directive), self.assertRaisesRegex(ValueError, 'RC import'):
                prepare_llvm.preparation_rc(directive)

    def test_archive_requires_successful_target_and_one_downloaded_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / 'compiler archive.tar.zst'
            archive.write_bytes(b'compiler')
            complete = {'id': {'targetCompleted': {'label': prepare_llvm.TARGET}},
                        'completed': {'success': True, 'outputGroup': [
                            {'name': 'default', 'fileSets': [{'id': 'root'}]}]}}
            outputs = [
                {'id': {'namedSet': {'id': 'root'}},
                 'namedSetOfFiles': {'fileSets': [{'id': 'leaf'}]}},
                {'id': {'namedSet': {'id': 'leaf'}},
                 'namedSetOfFiles': {'files': [{'uri': archive.as_uri()}]}},
            ]
            events = root / 'events.json'

            def write_events():
                events.write_text('\n'.join(json.dumps(event) for event in [complete, *outputs]))

            write_events()
            self.assertEqual(prepare_llvm.compiler_archive(events), archive)
            complete['completed']['success'] = False
            write_events()
            with self.assertRaisesRegex(ValueError, 'completed compiler archive'):
                prepare_llvm.compiler_archive(events)
            complete['completed']['success'] = True
            outputs[-1]['namedSetOfFiles']['files'].append({'uri': (root / 'extra.tar.zst').as_uri()})
            write_events()
            with self.assertRaisesRegex(ValueError, 'one completed compiler archive'):
                prepare_llvm.compiler_archive(events)
            outputs[-1]['namedSetOfFiles']['files'] = [{'uri': 'bytestream://upstream.example/compiler'}]
            write_events()
            with self.assertRaisesRegex(ValueError, 'downloaded locally'):
                prepare_llvm.compiler_archive(events)

    def test_source_checksum_checked_before_workspace_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / 'source.tar.gz'
            archive.write_bytes(b'wrong source')
            with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                prepare_llvm.source_workspace(archive, 'cxx')


if __name__ == '__main__':
    unittest.main()
