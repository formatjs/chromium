"""Fetch the pinned C++-trained compiler experiment through the read-only API."""

import argparse
import hashlib
import os
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revision', choices=[REVISION], required=True)
    parser.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    if args.destination.exists():
        raise FileExistsError(args.destination)
    key = os.environ.get('BUILDBUDDY_API_KEY', '')
    if not key:
        raise ValueError('BuildBuddy read-only key is not configured')
    args.destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=args.destination.parent) as temporary:
        archive = Path(temporary) / 'compiler.tar.zst'
        size, digest = 0, hashlib.sha256()
        with api_request('GetFile', {'uri': URI}, key) as response, archive.open('wb') as output:
            while chunk := response.read(1024 * 1024):
                size += len(chunk)
                if size > SIZE:
                    raise ValueError('Compiler archive exceeds pinned size')
                digest.update(chunk)
                output.write(chunk)
        if size != SIZE or digest.hexdigest() != SHA256:
            raise ValueError('Compiler archive SHA256/size mismatch')
        shutil.move(archive, args.destination)
    print('Verified compiler archive SHA256: ' + SHA256)


if __name__ == '__main__':
    main()
