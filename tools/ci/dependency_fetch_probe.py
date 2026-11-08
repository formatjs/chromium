"""Compare Python and Bazel dependency downloads on the same BB runner."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

from tools.ci.local_cold import BAZEL_SHA256, BAZEL_URL


ARCHIVES = (
    ('abseil-cpp', '20250814.1',
     'https://github.com/abseil/abseil-cpp/releases/download/20250814.1/abseil-cpp-20250814.1.tar.gz',
     '1692f77d1739bacf3f94337188b78583cf09bab7e420d2dc6c5605a4f86785a1'),
    ('bazel_features', '1.50.0',
     'https://github.com/bazel-contrib/bazel_features/releases/download/v1.50.0/bazel_features-v1.50.0.tar.gz',
     '094367e732ece23f334eaf84089a720b861d053beeba6a6a68356d3aee1dc32b'),
)


def download(url, destination, expected):
    digest = hashlib.sha256()
    with urllib.request.urlopen(url, timeout=60) as response, destination.open('wb') as output:
        while block := response.read(1024 * 1024):
            digest.update(block)
            output.write(block)
    if digest.hexdigest() != expected:
        raise ValueError('Dependency checksum mismatch')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', required=True, type=Path)
    args = parser.parse_args()
    args.directory.mkdir(parents=True, exist_ok=False)
    report = {'scope': 'Dependency transport diagnostic; no compilation or cold timing claim',
              'python': [], 'bazel': {}, 'complete': False}
    try:
        with tempfile.TemporaryDirectory(prefix='chromium-dependency-fetch-') as temporary:
            root = Path(temporary)
            bazel = root / 'bazel'
            download(BAZEL_URL, bazel, BAZEL_SHA256)
            bazel.chmod(0o755)
            for module, version, url, expected in ARCHIVES:
                row = {'module': module, 'version': version, 'expected_sha256': expected}
                started = time.monotonic()
                try:
                    path = root / (module + '.tar.gz')
                    download(url, path, expected)
                    row.update(success=True, bytes=path.stat().st_size)
                except urllib.error.HTTPError as error:
                    row.update(success=False, http_status=error.code)
                except urllib.error.URLError:
                    row.update(success=False, network_error=True)
                row['elapsed_seconds'] = time.monotonic() - started
                report['python'].append(row)
                print(json.dumps(row), flush=True)
            source = root / 'source'
            source.mkdir()
            (source / 'MODULE.bazel').write_text(''.join(
                'bazel_dep(name=' + repr(module) + ', version=' + repr(version) + ')\n'
                for module, version, _, _ in ARCHIVES))
            command = [str(bazel), '--ignore_all_rc_files', '--batch',
                       '--host_jvm_args=-Xmx2g', '--output_user_root=' + str(root / 'user'),
                       '--output_base=' + str(root / 'output'), '--install_base=' + str(root / 'install'),
                       'fetch', '--lockfile_mode=off', '--repository_cache=' + str(root / 'cache'),
                       '--repo_contents_cache='] + ['--repo=@@' + module + '+' for module, _, _, _ in ARCHIVES]
            started = time.monotonic()
            try:
                result = subprocess.run(command, cwd=source, capture_output=True, text=True, timeout=300)
                report['bazel'] = {'exit_code': result.returncode,
                                   'http_error_statuses': sorted(set(re.findall(
                                       r'GET returned (\d{3})', result.stderr)))}
            except subprocess.TimeoutExpired:
                report['bazel'] = {'timeout': True}
            report['bazel']['elapsed_seconds'] = time.monotonic() - started
            report['complete'] = True
    finally:
        (args.directory / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
