"""Compare gzip cost on one declared browser bundle without changing tar bytes."""

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import platform
import tempfile
import time
import zlib

from tools.ci.chromium import PLATFORMS, checksum, package_payload


def tar_digest(path):
    digest, size = hashlib.sha256(), 0
    with gzip.open(path, 'rb') as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return {'sha256': digest.hexdigest(), 'size_bytes': size}


def benchmark(bundle, target, directory):
    # Runfiles expose bundle directories through a symlink.
    bundle = bundle.resolve(strict=True)
    directory.mkdir(parents=True, exist_ok=True)
    report = {'platform': target['id'], 'python': platform.python_version(),
              'zlib': zlib.ZLIB_RUNTIME_VERSION, 'modes': []}
    with tempfile.TemporaryDirectory(prefix='chromium-compression-', dir=os.environ.get('TEST_TMPDIR')) as temporary:
        payload = Path(temporary) / 'payload.tar.gz'
        for level in (6, 1, 1, 6):
            wall, cpu = time.monotonic(), time.process_time()
            package_payload(bundle, payload, target, compression_level=level)
            mode = {'compression_level': level, 'wall_seconds': time.monotonic() - wall,
                    'cpu_seconds': time.process_time() - cpu,
                    'gzip_size_bytes': payload.stat().st_size, 'gzip_sha256': checksum(payload),
                    'tar': tar_digest(payload)}
            report['modes'].append(mode)
            (directory / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
            print(json.dumps(mode), flush=True)
            payload.unlink()
    report['tar_bytes_match'] = all(mode['tar'] == report['modes'][0]['tar'] for mode in report['modes'])
    report['repeated_gzip_bytes_match'] = all(
        report['modes'][a]['gzip_sha256'] == report['modes'][b]['gzip_sha256']
        for a, b in ((0, 3), (1, 2)))
    (directory / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    if not report['tar_bytes_match'] or not report['repeated_gzip_bytes_match']:
        raise ValueError('Compression changed tar bytes or repeated gzip output')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--platform', choices=sorted(PLATFORMS), required=True)
    parser.add_argument('--directory', type=Path,
                        default=os.environ.get('TEST_UNDECLARED_OUTPUTS_DIR'))
    args = parser.parse_args()
    if args.directory is None:
        parser.error('--directory or TEST_UNDECLARED_OUTPUTS_DIR is required')
    benchmark(args.bundle, PLATFORMS[args.platform], args.directory)


if __name__ == '__main__':
    main()
