import gzip
import hashlib
import io
import json
from pathlib import Path
import tempfile
import struct
import tarfile
import unittest
from unittest import mock

from tools.ci import compare_payloads as comparison
from tools.ci.chromium import PLATFORMS, stamp_payload
from tools.ci.compare_payloads import payload_digest


class PayloadComparisonTest(unittest.TestCase):
    def test_clean_cold_status_requires_matching_platform_and_success(self):
        platform, revision = 'darwin-arm64', '1' * 40
        url = 'https://formatjs.buildbuddy.io/invocation/cold'
        ordinary = {'context': 'Chromium cold build ' + platform, 'state': 'failure'}
        for context, state, succeeds in [
            ('Chromium clean cold build darwin-arm64', 'success', True),
            ('Chromium clean cold build darwin-arm64', 'pending', False),
            ('Chromium clean cold build linux-amd64', 'success', False),
            ('Other clean cold build darwin-arm64', 'success', False),
        ]:
            response = {'statuses': [ordinary, {'context': context, 'state': state, 'target_url': url}]}
            with self.subTest(context=context, state=state), \
                    mock.patch.dict(comparison.os.environ, {'GH_TOKEN': 'test-token'}), \
                    mock.patch.object(comparison.urllib.request, 'urlopen',
                                      return_value=io.BytesIO(json.dumps(response).encode())):
                if succeeds:
                    self.assertEqual(comparison.build_urls(revision, [platform], 'cold-browser'),
                                     {platform: url})
                else:
                    with self.assertRaisesRegex(ValueError, 'has not passed'):
                        comparison.build_urls(revision, [platform], 'cold-browser')

    def test_codeview_diagnostic_keeps_every_other_binary_byte(self):
        data = bytearray(1024)
        data[:2] = b'MZ'
        struct.pack_into('<I', data, 60, 64)
        data[64:68] = b'PE\0\0'
        struct.pack_into('<HHI', data, 68, 0x8664, 1, 123)
        struct.pack_into('<H', data, 84, 240)
        struct.pack_into('<H', data, 88, 0x20b)
        struct.pack_into('<II', data, 88 + 160, 4096, 28)
        data[328:334] = b'.rdata'
        struct.pack_into('<IIII', data, 336, 512, 4096, 512, 512)
        struct.pack_into('<IIII', data, 512 + 12, 2, 38, 0, 560)
        data[560:564] = b'RSDS'
        struct.pack_into('<I', data, 580, 1)
        data[584:598] = b'chrome.dll.pdb\0'
        original = comparison.pe_summary(data)
        data[564:580] = b'x' * 16
        changed = comparison.pe_summary(data)
        key = 'diagnostic_sha256_without_codeview_guid'
        self.assertEqual(original[key], changed[key])
        self.assertNotEqual(original['sections'], changed['sections'])
        self.assertNotEqual(original['codeview']['guid_hex'], changed['codeview']['guid_hex'])
        self.assertEqual(changed['codeview']['pdb_path'], 'chrome.dll.pdb')
        data[850] = 1
        self.assertNotEqual(original[key], comparison.pe_summary(data)[key])

    def test_pe_diagnostic_distinguishes_code_from_other_sections(self):
        data = bytearray(512)
        data[:2] = b'MZ'
        struct.pack_into('<I', data, 60, 64)
        data[64:68] = b'PE\0\0'
        struct.pack_into('<HHI', data, 68, 0x8664, 2, 123)
        for index, name in enumerate((b'.text', b'.rdata')):
            start = 88 + index * 40
            data[start:start + len(name)] = name
            struct.pack_into('<II', data, start + 16, 16, 256 + index * 16)
        original = comparison.pe_summary(data)
        data[275] = 1
        changed = comparison.pe_summary(data)
        self.assertEqual(original['sections'][0], changed['sections'][0])
        self.assertNotEqual(original['sections'][1]['sha256'], changed['sections'][1]['sha256'])
        self.assertEqual(changed['timestamp'], 123)
        struct.pack_into('<I', data, 88 + 16, len(data) + 1)
        with self.assertRaisesRegex(ValueError, 'section bounds'):
            comparison.pe_summary(data)

    def test_same_commit_cold_and_regular_builds_are_compared_independently(self):
        revision = '1' * 40
        platform = 'linux-amd64'
        with tempfile.TemporaryDirectory() as temporary, \
                mock.patch('sys.argv', ['compare', '--baseline', revision, '--revision', revision,
                                       '--revision-kind', 'cold-browser', '--platform', platform,
                                       '--directory', temporary]), \
                mock.patch.object(comparison, 'build_urls', side_effect=lambda rev, platforms, kind:
                                  {platform: 'https://example.test/' + kind}), \
                mock.patch.object(comparison, 'digest_artifact', side_effect=lambda url, rev, target, kind:
                                  {'sha256': kind, 'size_bytes': 100}) as digest:
            with self.assertRaisesRegex(ValueError, 'Browser payload bytes changed'):
                comparison.main()
            result = json.loads((Path(temporary) / 'payload-comparison.json').read_text())
            self.assertFalse(result['platforms'][platform]['payload_bytes_match'])
            digest.assert_has_calls([
                mock.call('https://example.test/browser', revision, platform, 'browser'),
                mock.call('https://example.test/cold-browser', revision, platform, 'cold-browser'),
            ], any_order=True)

    def archive(self, root, payload, revision):
        source = root / ('payload-' + revision + '.gz')
        source.write_bytes(gzip.compress(payload, mtime=0))
        return stamp_payload(source, root / revision, PLATFORMS['linux-amd64'], revision).read_bytes()

    def test_member_diagnostics_distinguish_compression_from_tar_changes(self):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode='w') as archive:
            member = tarfile.TarInfo('bundle/chrome')
            member.mode = 0o755
            member.size = 4
            archive.addfile(member, io.BytesIO(b'code'))
        tar = buffer.getvalue()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifests, digests = [], []
            for level in (1, 6):
                payload = root / f'payload-{level}.gz'
                payload.write_bytes(gzip.compress(tar, compresslevel=level, mtime=0))
                revision = str(level) * 40
                path = stamp_payload(payload, root / revision, PLATFORMS['linux-amd64'], revision)
                manifests.append(comparison.payload_manifest(path))
                with path.open('rb') as source:
                    digests.append(payload_digest(source, hashlib.sha256(path.read_bytes()).hexdigest(),
                                                  revision, 'linux-amd64'))
            self.assertNotEqual(digests[0], digests[1])
            self.assertEqual(manifests[0]['tar_sha256'], hashlib.sha256(tar).hexdigest())
            self.assertEqual(manifests[0]['tar_sha256'], manifests[1]['tar_sha256'])
            self.assertEqual(manifests[0]['members'], manifests[1]['members'])
            self.assertEqual(manifests[0]['members'][0]['sha256'], hashlib.sha256(b'code').hexdigest())
            self.assertEqual(manifests[0]['members'][0]['mode'], 0o755)

    def test_revision_changes_do_not_change_payload_digest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = self.archive(root, b'compiled browser bytes', '1' * 40)
            second = self.archive(root, b'compiled browser bytes', '2' * 40)
            changed = self.archive(root, b'different compiled browser bytes', '3' * 40)
            self.assertNotEqual(first, second)
            results = [payload_digest(io.BytesIO(data), hashlib.sha256(data).hexdigest(), revision * 40,
                                      'linux-amd64')
                       for data, revision in ((first, '1'), (second, '2'), (changed, '3'))]
            self.assertEqual(results[0], results[1])
            self.assertNotEqual(results[0], results[2])

    def test_checksum_and_stamp_are_required(self):
        with tempfile.TemporaryDirectory() as temporary:
            data = self.archive(Path(temporary), b'compiled browser bytes', '1' * 40)
            checksum = hashlib.sha256(data).hexdigest()
            for content, expected, revision in ((data[:-5], checksum, '1' * 40),
                                                (data, '0' * 64, '1' * 40),
                                                (data, checksum, '2' * 40)):
                with self.subTest(revision=revision, truncated=len(content) != len(data)):
                    with self.assertRaises(ValueError):
                        payload_digest(io.BytesIO(content), expected, revision, 'linux-amd64')

    def test_unbounded_stamp_is_rejected_before_payload_processing(self):
        data = gzip.compress(b'x' * 100000, mtime=0)
        with self.assertRaisesRegex(ValueError, 'stamp exceeds'):
            payload_digest(io.BytesIO(data), hashlib.sha256(data).hexdigest(), '1' * 40, 'linux-amd64')


if __name__ == '__main__':
    unittest.main()
