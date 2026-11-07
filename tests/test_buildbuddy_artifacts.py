import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tools.ci import buildbuddy_artifacts as artifacts


REVISION = '1' * 40
IDENTIFIER = '01234567-89ab-cdef-0123-456789abcdef'
URL = 'https://formatjs.buildbuddy.io/invocation/' + IDENTIFIER
TARGET = 'linux-amd64'
ARCHIVE = 'chromium-linux-amd64.tar.gz'


def invocation():
    return {'invocation': [{
        'commitSha': REVISION,
        'repoUrl': 'https://github.com/formatjs/chromium.git',
        'pattern': 'Chromium ' + TARGET,
        'success': True,
        'invocationStatus': 'COMPLETE_INVOCATION_STATUS',
        'artifacts': [
            {'name': TARGET + '/' + name,
             'uri': 'bytestream://formatjs.buildbuddy.io/blobs/' + str(index)}
            for index, name in enumerate([ARCHIVE, ARCHIVE + '.sha256'])
        ],
    }]}


class BuildBuddyArtifactsTest(unittest.TestCase):
    def test_invocation_url_requires_formatjs_host(self):
        self.assertEqual(artifacts.invocation_id(URL), IDENTIFIER)
        for url in [URL.replace('https:', 'http:'),
                    URL.replace('formatjs.buildbuddy.io', 'attacker.example'),
                    URL + '?redirect=other', URL + '/extra']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                artifacts.invocation_id(url)

    def test_invocation_must_match_successful_repo_commit_and_platform(self):
        changes = [
            {'commitSha': '2' * 40}, {'repoUrl': 'https://github.com/other/repo'},
            {'pattern': 'Chromium windows-amd64'}, {'success': False},
            {'invocationStatus': 'PARTIAL_INVOCATION_STATUS'},
        ]
        for change in changes:
            response = invocation()
            response['invocation'][0].update(change)
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, 'successful commit'):
                artifacts.artifact_uris(response, REVISION, TARGET)

    def test_missing_duplicate_or_foreign_artifacts_rejected(self):
        good = invocation()
        variants = [copy.deepcopy(good) for _ in range(3)]
        variants[0]['invocation'][0]['artifacts'].pop()
        variants[1]['invocation'][0]['artifacts'].append(
            copy.deepcopy(good['invocation'][0]['artifacts'][0]))
        variants[2]['invocation'][0]['artifacts'][0]['uri'] = 'https://attacker.example/file'
        for response in variants:
            with self.subTest(response=response), self.assertRaises(ValueError):
                artifacts.artifact_uris(response, REVISION, TARGET)

    def test_cold_browser_keeps_provenance_checks_and_cannot_impersonate_regular_build(self):
        for prefix in ('Chromium cold build ', 'Chromium clean cold build '):
            with self.subTest(prefix=prefix):
                self.check_cold_browser_provenance(prefix)

    def check_cold_browser_provenance(self, prefix):
        response = invocation()
        response['invocation'][0]['pattern'] = prefix + TARGET
        self.assertEqual(set(artifacts.artifact_uris(response, REVISION, TARGET, kind='cold-browser')),
                         {ARCHIVE, ARCHIVE + '.sha256'})
        with self.assertRaisesRegex(ValueError, 'successful commit'):
            artifacts.artifact_uris(response, REVISION, TARGET)
        response['invocation'][0]['success'] = False
        with self.assertRaisesRegex(ValueError, 'successful commit'):
            artifacts.artifact_uris(response, REVISION, TARGET, kind='cold-browser')

    def test_download_checks_digest_before_publishing_files(self):
        payload = b'compressed browser artifact'
        digest = (hashlib.sha256(payload).hexdigest() + '\n').encode()
        for checksum, succeeds in [(digest, True), (b'0' * 64 + b'\n', False)]:
            with self.subTest(succeeds=succeeds), tempfile.TemporaryDirectory() as directory:
                destination = Path(directory) / 'download'
                replies = [io.BytesIO(json.dumps(invocation()).encode()),
                           io.BytesIO(payload), io.BytesIO(checksum)]
                with mock.patch.object(artifacts, 'api_request', side_effect=replies) as request:
                    if succeeds:
                        artifacts.download(URL, REVISION, TARGET, destination, 'read-only-test-key')
                        self.assertEqual((destination / ARCHIVE).read_bytes(), payload)
                    else:
                        with self.assertRaisesRegex(ValueError, 'SHA256 mismatch'):
                            artifacts.download(URL, REVISION, TARGET, destination, 'read-only-test-key')
                        self.assertFalse(destination.exists())
                request.assert_has_calls([
                    mock.call('GetInvocation', {
                        'selector': {'invocation_id': IDENTIFIER}, 'include_artifacts': True,
                    }, 'read-only-test-key'),
                    mock.call('GetFile', {'uri': 'bytestream://formatjs.buildbuddy.io/blobs/0'},
                              'read-only-test-key'),
                    mock.call('GetFile', {'uri': 'bytestream://formatjs.buildbuddy.io/blobs/1'},
                              'read-only-test-key'),
                ])

    def test_cold_browser_download_uses_browser_archive_name(self):
        payload = b'cold browser artifact'
        response = invocation()
        response['invocation'][0]['pattern'] = 'Chromium cold build ' + TARGET
        replies = [io.BytesIO(json.dumps(response).encode()), io.BytesIO(payload),
                   io.BytesIO((hashlib.sha256(payload).hexdigest() + '\n').encode())]
        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.object(artifacts, 'api_request', side_effect=replies):
            destination = Path(directory) / 'download'
            artifacts.download(URL, REVISION, TARGET, destination, 'read-only-test-key', kind='cold-browser')
            self.assertEqual((destination / ARCHIVE).read_bytes(), payload)

    def test_oversized_download_leaves_no_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / 'download'
            replies = [io.BytesIO(json.dumps(invocation()).encode()), io.BytesIO(b'12345')]
            with mock.patch.object(artifacts, 'api_request', side_effect=replies), \
                    mock.patch.object(artifacts, 'MAX_ARCHIVE_BYTES', 4):
                with self.assertRaisesRegex(ValueError, 'size limit'):
                    artifacts.download(URL, REVISION, TARGET, destination, 'read-only-test-key')
            self.assertEqual(list(Path(directory).iterdir()), [])


if __name__ == '__main__':
    unittest.main()
