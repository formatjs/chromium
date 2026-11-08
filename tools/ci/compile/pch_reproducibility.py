"""Check the pinned compiler's PCH bytes and header-content validation."""

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[3]


def verify_producer_options(arguments):
    flag = '-fno-pch-timestamp'
    index = arguments.index(flag) if arguments.count(flag) == 1 else -1
    if (index < 1 or arguments[index - 1] != '-Xclang'
            or arguments.count('-fpch-validate-input-files-content') != 1
            or arguments.count('--relocatable-pch') != 1):
        raise ValueError('PCH producer must omit timestamps and validate input content')
    if '-fno-validate-pch' in arguments or '-disable-pch-validation' in arguments:
        raise ValueError('PCH validation bypass is forbidden')


def verify(compiler, directory, expected_sha256):
    compiler = compiler.absolute()
    if hashlib.sha256(compiler.read_bytes()).hexdigest() != expected_sha256:
        raise ValueError('PCH check compiler checksum differs')
    tree = ast.parse((ROOT / 'overlays/chromium/bcr/overlay/native/pch_flags.bzl').read_text())
    flags = {node.targets[0].id: ast.literal_eval(node.value) for node in tree.body
             if isinstance(node, ast.Assign)}
    producer = flags['PCH_PRODUCER_FLAGS']
    consumer = flags['PCH_CONSUMER_FLAGS']
    verify_producer_options(producer)
    directory.mkdir(parents=True, exist_ok=False)
    temporary = directory / 'tmp'
    temporary.mkdir()
    environment = {'PATH': os.defpath, 'LC_ALL': 'C', 'TMPDIR': str(temporary)}
    common = [str(compiler), '-std=c++20', '-nostdinc', '-nostdinc++', '-isysroot', '.']

    def run(arguments, cwd, rejection=False):
        result = subprocess.run(common + arguments, cwd=cwd, env=environment,
                                capture_output=True, text=True)
        if rejection:
            if result.returncode == 0 or 'content changed' not in result.stderr:
                raise ValueError('PCH accepted modified header content')
        elif result.returncode:
            raise ValueError('PCH check failed: ' + result.stderr[-2000:])

    hashes = []
    for index, name in enumerate(('left', 'right')):
        root = directory / name
        root.mkdir()
        header = root / 'sample.h'
        header.write_text('#pragma once\ninline int sample() { return 7; }\n')
        os.utime(header, (1000000000 + index * 100, 1000000000 + index * 100))
        (root / 'source.cc').write_text('int result() { return sample(); }\n')
        run(producer + ['sample.h', '-o', 'sample.pch'], root)
        hashes.append(hashlib.sha256((root / 'sample.pch').read_bytes()).hexdigest())
    if hashes[0] != hashes[1]:
        raise ValueError('PCH bytes depend on checkout directory or header mtime')
    run(consumer + ['-include-pch', '../left/sample.pch', '-c', 'source.cc', '-o', 'relocated.o'],
        directory / 'right')
    header = directory / 'left/sample.h'
    header.write_text('#pragma once\ninline int sample() { return 8; }\n')
    for timestamp in (1000000000, 0):
        os.utime(header, (timestamp, timestamp))
        run(consumer + ['-include-pch', 'sample.pch', '-c', 'source.cc', '-o', 'modified.o'],
            directory / 'left', rejection=True)
    report = {'scope': 'Pinned compiler PCH check; not Chromium cold timing',
              'compiler_sha256': expected_sha256, 'reproducible_across_roots_and_mtimes': True,
              'relocated_unchanged_content_accepted': True,
              'modified_same_size_content_rejected': True,
              'modified_zero_mtime_content_rejected': True}
    (directory / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', type=Path, required=True)
    parser.add_argument('--expected-sha256', required=True)
    parser.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.compiler, args.directory.resolve(), args.expected_sha256)))


if __name__ == '__main__':
    main()
