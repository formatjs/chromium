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

BOLT_REVISION = '8b5a3e46bef60e25664d77e217b7930ac866bca5'
BOLT_TOOLS = {
    'llvm-unstripped': {
        'sha256': '8f36676d15302d2e509a145d50671e31d593816ec373fc7fd0a3e0136a316ef6',
        'size': 212232440,
    },
    'llvm-bolt': {
        'sha256': '096a2e6f1360c4180fd02aa5be8ed42dac3695024c846ca62e1c7c7a2d834b5e',
        'size': 65016168,
    },
}


BOLT_RELOCATION_REVISION = '722e9b7c34c222071feaffed904e5bc2b9aba89b'
BOLT_RELOCATION_TOOLS = {
    'llvm-with-relocations': {
        'sha256': '9e8ed3ed09c3438e6a568778014309fa54ade790b09e67e005e7c7094ae81c2a',
        'size': 282458312,
        'uri': ('bytestream://remote.buildbuddy.io/bb-snapshot/'
                'ea99aeae9a2016c04e6c62748864afce336069e47b420523a08803c1b0682571/'
                'blobs/9e8ed3ed09c3438e6a568778014309fa54ade790b09e67e005e7c7094ae81c2a/282458312'),
    },
    'libbolt_rt_instr.a': {
        'sha256': 'bf426b1c2eed618182d0fc3d21b4737ee85cab896145cc4e8f81a798f54cba81',
        'size': 35380,
        'uri': ('bytestream://formatjs.buildbuddy.io/compiler-training-35bd1a8/blobs/'
                'bf426b1c2eed618182d0fc3d21b4737ee85cab896145cc4e8f81a798f54cba81/35380'),
    },
}
BOLT_PREPARATIONS = {
    BOLT_REVISION: {'tools': BOLT_TOOLS, 'invocation': 'ec9d3a07-694e-42a0-8ef5-6dcc60d01ba8'},
    BOLT_RELOCATION_REVISION: {'tools': BOLT_RELOCATION_TOOLS, 'invocation': 'c7838bd8-259c-4820-afad-50be84b3d75d'},
}


def archive_spec(revision, key, *, spec=None, prefix='llvm-compiler', max_size=128 * 1024 * 1024):
    spec = dict(EXPERIMENTS[revision] if spec is None else spec)
    if 'uri' in spec:
        return spec
    with api_request('GetInvocation', {
            'selector': {'invocation_id': spec['invocation']}, 'include_artifacts': True}, key) as response:
        invocations = json.load(response).get('invocation', [])
    suffix = prefix + '/' + spec['name']
    matches = [artifact for invocation in invocations for artifact in invocation.get('artifacts', [])
               if artifact.get('name', '') == suffix or artifact.get('name', '').endswith('/' + suffix)]
    if len(matches) != 1:
        raise ValueError('Expected one pinned compiler archive artifact')
    uri = matches[0]['uri']
    parsed = urllib.parse.urlsplit(uri)
    parts = parsed.path.rsplit('/', 2)
    if (parsed.scheme != 'bytestream' or parsed.netloc not in ('remote.buildbuddy.io', 'formatjs.buildbuddy.io')
            or len(parts) != 3 or parts[-2] != spec['sha256']):
        raise ValueError('Compiler artifact URI does not match pinned digest')
    size = int(parts[-1])
    if not 0 < size <= max_size or ('size' in spec and size != spec['size']):
        raise ValueError('Compiler artifact size outside expected bound')
    spec.update(uri=uri, size=size)
    return spec


def download(spec, destination, key):
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as temporary:
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
        shutil.move(archive, destination)
    print('Verified compiler artifact SHA256: ' + spec['sha256'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revision', choices=sorted(set(EXPERIMENTS) | set(BOLT_PREPARATIONS)), required=True)
    output = parser.add_mutually_exclusive_group(required=True)
    output.add_argument('--destination', type=Path)
    output.add_argument('--directory', type=Path)
    args = parser.parse_args()
    if args.revision in BOLT_PREPARATIONS and args.destination:
        parser.error('BOLT tools require --directory')
    key = os.environ.get('BUILDBUDDY_API_KEY', '')
    if not key:
        raise ValueError('BuildBuddy read-only key is not configured')
    if args.revision in BOLT_PREPARATIONS:
        preparation = BOLT_PREPARATIONS[args.revision]
        specs = [archive_spec(None, key, spec=values | {
            'name': name, 'invocation': preparation['invocation']},
            prefix='llvm-bolt', max_size=512 * 1024 * 1024) for name, values in preparation['tools'].items()]
        for spec in specs:
            download(spec, args.directory / spec['name'], key)
    else:
        destination = args.destination or args.directory / EXPERIMENTS[args.revision]['name']
        download(archive_spec(args.revision, key), destination, key)


if __name__ == '__main__':
    main()
