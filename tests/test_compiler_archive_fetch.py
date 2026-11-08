from contextlib import redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tools.ci import compiler_archive


class CompilerArchiveFetchTest(unittest.TestCase):
    def test_candidate_metadata_and_download_must_match_pinned_digest(self):
        payload = b'compiler archive bytes'
        digest = hashlib.sha256(payload).hexdigest()
        spec = {'name': 'compiler.tar.zst', 'sha256': digest, 'invocation': 'compiler-build'}
        uri = 'bytestream://remote.buildbuddy.io/instance/blobs/' + digest + '/' + str(len(payload))
        artifacts = {'invocation': [{'artifacts': [
            {'name': 'llvm-compiler/compiler.tar.zst', 'uri': uri}]}]}
        for content in [payload, b'x' * len(payload)]:
            with self.subTest(tampered=content != payload), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                with mock.patch.dict(compiler_archive.EXPERIMENTS, {'test': spec}, clear=True), \
                        mock.patch.dict(os.environ, {'BUILDBUDDY_API_KEY': 'read-only-test-key'}), \
                        mock.patch('sys.argv', ['fetch', '--revision', 'test', '--directory', str(root)]), \
                        mock.patch.object(compiler_archive, 'api_request', side_effect=[
                            io.BytesIO(json.dumps(artifacts).encode()), io.BytesIO(content)]), \
                        redirect_stdout(io.StringIO()):
                    if content == payload:
                        compiler_archive.main()
                        self.assertEqual((root / 'compiler.tar.zst').read_bytes(), payload)
                    else:
                        with self.assertRaisesRegex(ValueError, 'mismatch'):
                            compiler_archive.main()
                        self.assertFalse((root / 'compiler.tar.zst').exists())

    def test_unpinned_or_ambiguous_candidate_artifacts_are_rejected(self):
        revision = compiler_archive.CANDIDATE_REVISION
        spec = compiler_archive.EXPERIMENTS[revision]
        base = 'bytestream://remote.buildbuddy.io/instance/blobs/'
        valid = {'name': 'command-0/llvm-compiler/' + spec['name'],
                 'uri': base + spec['sha256'] + '/40000000'}
        for artifacts in [[], [valid, valid], [valid | {'uri': base + '0' * 64 + '/40000000'}],
                          [valid | {'uri': base + spec['sha256'] + '/0'}],
                          [valid | {'uri': base + spec['sha256'] + '/200000000'}]]:
            response = {'invocation': [{'artifacts': artifacts}]}
            with self.subTest(artifacts=artifacts), \
                    mock.patch.object(compiler_archive, 'api_request', return_value=io.BytesIO(json.dumps(response).encode())):
                with self.assertRaises(ValueError):
                    compiler_archive.archive_spec(revision, 'read-only-test-key')


if __name__ == '__main__':
    unittest.main()
