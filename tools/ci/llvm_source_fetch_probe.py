"""Compare verified LLVM source downloads on BB; no compilation or cold timing claim."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import time
import urllib.error

from tools.ci.dependency_fetch_probe import download
from tools.ci.local_cold import BAZEL_SHA256, BAZEL_URL

URL = 'https://github.com/hermeticbuild/llvm-redist/releases/download/llvmorg-23.1.2-r1/llvm-project-23.1.2.src.tar.zst'
SHA256 = '271da53a2feb0cb221a9276a14268a3b76ad802c7fc8fb1098291a43b06e4c56'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', required=True, type=Path)
    args = parser.parse_args()
    args.directory.mkdir(parents=True, exist_ok=False)
    report = {'scope': __doc__, 'url': URL, 'expected_sha256': SHA256, 'complete': False}
    try:
        with tempfile.TemporaryDirectory(prefix='chromium-llvm-fetch-') as temporary:
            root = Path(temporary)
            bazel = root / 'bazel'
            download(BAZEL_URL, bazel, BAZEL_SHA256)
            bazel.chmod(0o755)
            started = time.monotonic()
            try:
                archive = root / 'python-llvm.tar.zst'
                download(URL, archive, SHA256)
                report['python'] = {'success': True, 'bytes': archive.stat().st_size}
            except urllib.error.HTTPError as error:
                report['python'] = {'success': False, 'http_status': error.code}
            except urllib.error.URLError:
                report['python'] = {'success': False, 'network_error': True}
            report['python']['elapsed_seconds'] = time.monotonic() - started
            print(json.dumps(report['python']), flush=True)
            source = root / 'source'
            source.mkdir()
            (source / 'MODULE.bazel').write_text(
                'http_file = use_repo_rule("@bazel_tools//tools/build_defs/repo:http.bzl", "http_file")\n'
                'http_file(name="llvm_source", urls=[' + repr(URL) + '], sha256=' + repr(SHA256) + ')\n')
            command = [str(bazel), '--ignore_all_rc_files', '--batch',
                       '--host_jvm_args=-Xmx2g', '--output_user_root=' + str(root / 'user'),
                       '--output_base=' + str(root / 'output'), '--install_base=' + str(root / 'install'),
                       'fetch', '--lockfile_mode=off', '--repository_cache=' + str(root / 'cache'),
                       '--repo_contents_cache=', '--repo=@llvm_source']
            started = time.monotonic()
            with (args.directory / 'bazel.log').open('w') as log:
                result = subprocess.run(command, cwd=source, stdout=log, stderr=subprocess.STDOUT)
            report['bazel'] = {'exit_code': result.returncode, 'elapsed_seconds': time.monotonic() - started}
            if result.returncode == 0:
                files = list((root / 'output/external').glob('*/file/downloaded'))
                assert len(files) == 1, 'Missing downloaded LLVM archive'
                with files[0].open('rb') as stream:
                    actual = hashlib.file_digest(stream, 'sha256').hexdigest()
                assert actual == SHA256, 'Bazel LLVM archive checksum mismatch'
                report['bazel'].update(sha256=actual, bytes=files[0].stat().st_size)
            report['complete'] = True
    finally:
        (args.directory / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
