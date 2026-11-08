"""Fetch the pinned C++-trained compiler experiment through the read-only API."""

import argparse
import hashlib
import os
import json
import urllib.parse
from pathlib import Path
import shutil
import tempfile

from tools.ci.buildbuddy_artifacts import api_request


REVISION = '366173ffc47d1a12a92c32d542c39c24b80fea28'
SHA256 = 'adbc348d20518481b44be46c21440c8aec541572014a86614248c3db2b46cc5c'
SIZE = 39193174
URI = ('bytestream://remote.buildbuddy.io/bb-snapshot/'
       '02243316ca41f110bb13a141260f7622b9bf21b294f56e1c6fb4b0e2fbaf52b9/'
       'blobs/' + SHA256 + '/' + str(SIZE))


CANDIDATE_REVISION = 'dc5ddb5ec6409e5d8f086f68489f4419921761e8'
CANDIDATE_SHA256 = 'c04cdca0eb8f94a93a2193200f5375356c7769cb53d3eb42ef75fd7ac95f0fa0'
EXPERIMENTS = {
    REVISION: {'name': 'llvm-23.1.2-linux-amd64-cxx.tar.zst', 'sha256': SHA256, 'size': SIZE, 'uri': URI},
    CANDIDATE_REVISION: {
        'name': 'llvm-23.1.2-linux-amd64-chromium.tar.zst', 'sha256': CANDIDATE_SHA256,
        'invocation': '13718153-9a1e-4774-80d4-51299ca93613',
    },
}


def archive_spec(revision, key):
    spec = dict(EXPERIMENTS[revision])
    if 'uri' in spec:
        return spec
    with api_request('GetInvocation', {
            'selector': {'invocation_id': spec['invocation']}, 'include_artifacts': True}, key) as response:
        invocations = json.load(response).get('invocation', [])
    suffix = '/llvm-compiler/' + spec['name']
    matches = [artifact for invocation in invocations for artifact in invocation.get('artifacts', [])
               if artifact.get('name', '').endswith(suffix)]
    if len(matches) != 1:
        raise ValueError('Expected one pinned compiler archive artifact')
    uri = matches[0]['uri']
    parsed = urllib.parse.urlsplit(uri)
    parts = parsed.path.rsplit('/', 2)
    if parsed.scheme != 'bytestream' or len(parts) != 3 or parts[-2] != spec['sha256']:
        raise ValueError('Compiler artifact URI does not match pinned digest')
    size = int(parts[-1])
    if not 0 < size <= 128 * 1024 * 1024:
        raise ValueError('Compiler artifact size outside expected bound')
    spec.update(uri=uri, size=size)
    return spec


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revision', choices=sorted(EXPERIMENTS), required=True)
    output = parser.add_mutually_exclusive_group(required=True)
    output.add_argument('--destination', type=Path)
    output.add_argument('--directory', type=Path)
    args = parser.parse_args()
    args.destination = args.destination or args.directory / EXPERIMENTS[args.revision]['name']
    if args.destination.exists() or args.destination.is_symlink():
        raise FileExistsError(args.destination)
    key = os.environ.get('BUILDBUDDY_API_KEY', '')
    if not key:
        raise ValueError('BuildBuddy read-only key is not configured')
    spec = archive_spec(args.revision, key)
    args.destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=args.destination.parent) as temporary:
        archive = Path(temporary) / 'compiler.tar.zst'
        size, digest = 0, hashlib.sha256()
        with api_request('GetFile', {'uri': spec['uri']}, key) as response, archive.open('wb') as output:
            while chunk := response.read(1024 * 1024):
                size += len(chunk)
                if size > spec['size']:
                    raise ValueError('Compiler archive exceeds pinned size')
                digest.update(chunk)
                output.write(chunk)
        if size != spec['size'] or digest.hexdigest() != spec['sha256']:
            raise ValueError('Compiler archive SHA256/size mismatch')
        shutil.move(archive, args.destination)
    print('Verified compiler archive SHA256: ' + spec['sha256'])


if __name__ == '__main__':
    main()
