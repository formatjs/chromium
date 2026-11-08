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
    def test_bolt_pair_downloads_only_verified_pinned_files(self):
        payloads = {'llvm-unstripped': b'compiler with symbols', 'llvm-bolt': b'binary optimizer'}
        specs = {name: {'sha256': hashlib.sha256(payload).hexdigest(), 'size': len(payload)}
                 for name, payload in payloads.items()}
        artifacts = {'invocation': [{'artifacts': [
            {'name': 'command-0/llvm-bolt/' + name,
             'uri': 'bytestream://remote.buildbuddy.io/instance/blobs/' + spec['sha256'] + '/' + str(spec['size'])}
            for name, spec in specs.items()]}]}
        metadata = json.dumps(artifacts).encode()
        for tamper in [False, True]:
            with self.subTest(tamper=tamper), tempfile.TemporaryDirectory() as temporary:
                responses = [io.BytesIO(metadata), io.BytesIO(metadata),
                             io.BytesIO(payloads['llvm-unstripped']),
                             io.BytesIO(b'x' * len(payloads['llvm-bolt']) if tamper else payloads['llvm-bolt'])]
                with mock.patch.dict(compiler_archive.BOLT_TOOLS, specs, clear=True), \
                        mock.patch.dict(os.environ, {'BUILDBUDDY_API_KEY': 'read-only-test-key'}), \
                        mock.patch('sys.argv', ['fetch', '--revision', compiler_archive.BOLT_REVISION,
                                                '--directory', temporary]), \
                        mock.patch.object(compiler_archive, 'api_request', side_effect=responses), \
                        redirect_stdout(io.StringIO()):
                    if tamper:
                        with self.assertRaisesRegex(ValueError, 'mismatch'):
                            compiler_archive.main()
                        self.assertFalse((Path(temporary) / 'llvm-bolt').exists())
                    else:
                        compiler_archive.main()
                        for name, payload in payloads.items():
                            self.assertEqual((Path(temporary) / name).read_bytes(), payload)

    def test_bolt_metadata_cannot_change_host_or_pinned_size(self):
        spec = dict(compiler_archive.BOLT_TOOLS['llvm-bolt'], name='llvm-bolt', invocation='preparation')
        base = 'bytestream://remote.buildbuddy.io/instance/blobs/' + spec['sha256'] + '/'
        for uri in [base + str(spec['size'] + 1), base.replace('remote.buildbuddy.io', 'unexpected.example') + str(spec['size'])]:
            response = {'invocation': [{'artifacts': [{'name': 'llvm-bolt/llvm-bolt', 'uri': uri}]}]}
            with self.subTest(uri=uri), mock.patch.object(compiler_archive, 'api_request',
                    return_value=io.BytesIO(json.dumps(response).encode())):
                with self.assertRaises(ValueError):
                    compiler_archive.archive_spec(None, 'read-only-test-key', spec=spec,
                                                 prefix='llvm-bolt', max_size=256 * 1024 * 1024)

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
