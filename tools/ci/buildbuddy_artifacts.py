"""Download verified Chromium artifacts without running build-branch code."""

import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
import urllib.parse
import urllib.request

from tools.ci.chromium import PLATFORMS, checksum


API_URL = 'https://formatjs.buildbuddy.io/api/v1/'
MAX_ARCHIVE_BYTES = 4 * 1024 * 1024 * 1024
COLD_WORKFLOW_PREFIXES = ('Chromium cold build ', 'Chromium clean cold build ',
                          'Chromium strict cold build ')


def invocation_id(url):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or parsed.netloc != 'formatjs.buildbuddy.io':
        raise ValueError('Unexpected BuildBuddy invocation host')
    match = re.fullmatch(r'/invocation/([0-9a-f-]{36})', parsed.path)
    if not match or parsed.query or parsed.fragment:
        raise ValueError('Invalid BuildBuddy invocation URL')
    return match.group(1)


def artifact_uris(response, revision, target, kind='browser'):
    if target not in PLATFORMS or not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise ValueError('Invalid artifact platform or commit')
    prefixes = {'browser': ('Chromium ',), 'components': ('Chromium components ',),
                'cold-browser': COLD_WORKFLOW_PREFIXES}
    if kind not in prefixes:
        raise ValueError('Invalid artifact kind')
    invocations = response.get('invocation', [])
    if len(invocations) != 1:
        raise ValueError('Expected exactly one BuildBuddy invocation')
    invocation = invocations[0]
    if (invocation.get('commitSha') != revision
            or invocation.get('repoUrl', '').removesuffix('.git')
            != 'https://github.com/formatjs/chromium'
            or invocation.get('pattern') not in [prefix + target for prefix in prefixes[kind]]
            or not invocation.get('success')
            or invocation.get('invocationStatus') != 'COMPLETE_INVOCATION_STATUS'):
        raise ValueError('Cross-build invocation does not match successful commit')
    archive = 'chromium-' + ('components-' if kind == 'components' else '') + target + '.tar.gz'
    uris = {}
    for name in [archive, archive + '.sha256']:
        artifacts = [item for item in invocation.get('artifacts', [])
                     if PurePosixPath(item.get('name', '')).name == name]
        if len(artifacts) != 1:
            raise ValueError('Expected exactly one artifact: ' + name)
        uri = artifacts[0].get('uri', '')
        parsed = urllib.parse.urlsplit(uri)
        if parsed.scheme != 'bytestream' or parsed.netloc not in (
                'formatjs.buildbuddy.io', 'remote.buildbuddy.io'):
            raise ValueError('Unexpected BuildBuddy artifact URI')
        uris[name] = uri
    return uris


def api_request(method, body, key):
    request = urllib.request.Request(
        API_URL + method, data=json.dumps(body).encode(),
        headers={'Content-Type': 'application/json', 'x-buildbuddy-api-key': key},
    )
    return urllib.request.urlopen(request, timeout=120)


def download(url, revision, target, destination, key, kind='browser'):
    if not key:
        raise ValueError('BuildBuddy read-only key is not configured')
    identifier = invocation_id(url)
    with api_request('GetInvocation', {
        'selector': {'invocation_id': identifier}, 'include_artifacts': True,
    }, key) as response:
        uris = artifact_uris(json.load(response), revision, target, kind)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(destination)
    with tempfile.TemporaryDirectory(dir=destination.parent) as temporary:
        staging = Path(temporary) / 'artifacts'
        staging.mkdir()
        for name, uri in uris.items():
            limit = 65 if name.endswith('.sha256') else MAX_ARCHIVE_BYTES
            total = 0
            with api_request('GetFile', {'uri': uri}, key) as response, \
                    (staging / name).open('wb') as output:
                while chunk := response.read(1024 * 1024):
                    total += len(chunk)
                    if total > limit:
                        raise ValueError('Artifact exceeds size limit: ' + name)
                    output.write(chunk)
        archive = staging / ('chromium-' + ('components-' if kind == 'components' else '') + target + '.tar.gz')
        expected = archive.with_suffix('.gz.sha256').read_text().strip()
        if not re.fullmatch(r'[0-9a-f]{64}', expected) or checksum(archive) != expected:
            raise ValueError('Artifact SHA256 mismatch')
        staging.rename(destination)


def main():
    download(os.environ['INVOCATION_URL'], os.environ['BUILD_SHA'],
             os.environ['TARGET_PLATFORM'], Path(os.environ['ARTIFACT_DIRECTORY']),
             os.environ.get('BUILDBUDDY_API_KEY', ''), os.environ.get('ARTIFACT_KIND', 'browser'))


if __name__ == '__main__':
    main()
