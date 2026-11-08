"""Check lazy Bats registration and execute its original runtime and helpers."""

import argparse
from contextlib import contextmanager
import hashlib
import http.server
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import urllib.request

from tools.ci.local_cold import BAZEL_SHA256


ARCHIVES = {
    'core': ('v1.10.0', 'a1a9f7875aa4b6a9480ca384d5865f1ccf1b0b1faead6b47aa47d79709a5c5fd'),
    'support': ('v0.3.0', '7815237aafeb42ddcc1b8c698fc5808026d33317d8701d5ec2396e9634e2918f'),
    'assert': ('v2.1.0', '98ca3b685f8b8993e48ec057565e6e2abcc541034ed5b0e81f191505682037fd'),
    'file': ('v0.4.0', '9b69043241f3af1c2d251f89b4fcafa5df3f05e97b89db18d7c9bdf5731bb27a'),
}
MODULE = '''bazel_dep(name="bazel_lib", version="3.3.1")
bazel_dep(name="platforms", version="1.1.0")
register_toolchains("//:probe_registration")
'''
RULES = '''def _toolchain_impl(ctx):
    return [platform_common.ToolchainInfo()]

probe_toolchain = rule(implementation = _toolchain_impl)

def _probe_impl(ctx):
    return [DefaultInfo()]

probe = rule(implementation = _probe_impl, toolchains = ["//:probe_type"])
'''
BUILD = '''load(":probe.bzl", "probe", "probe_toolchain")
toolchain_type(name="probe_type")
probe_toolchain(name="probe_implementation")
toolchain(name="probe_registration", toolchain_type=":probe_type", toolchain=":probe_implementation")
probe(name="probe")
'''
SMOKE = '''@test "core and helper libraries still work" {
    bats_load_library bats-support
    bats_load_library bats-assert
    bats_load_library bats-file
    run printf '%s' 'ok'
    assert_success
    assert_output 'ok'
}
'''


def copy_archive_cache(original, destination):
    excluded = {sha for _, sha in ARCHIVES.values()}
    for directory in (original / 'content_addressable/sha256').iterdir():
        if not directory.is_dir() or directory.name in excluded:
            continue
        for file in directory.iterdir():
            if not file.is_file():
                continue
            target = destination / 'content_addressable/sha256' / directory.name / file.name
            target.parent.mkdir(parents=True, exist_ok=True)
            # Share immutable archive bytes; keep independent cache metadata.
            if file.name == 'file':
                os.link(file, target)
            else:
                shutil.copy2(file, target)


def archive_inputs(cache):
    payloads = {}
    for name, (version, expected) in ARCHIVES.items():
        cached = cache / 'content_addressable/sha256' / expected / 'file'
        if cached.is_file():
            data = cached.read_bytes()
        else:
            url = 'https://codeload.github.com/bats-core/bats-' + name + '/tar.gz/' + version
            with urllib.request.urlopen(url, timeout=60) as response:
                data = response.read()
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError('Bats archive checksum mismatch: ' + name)
        payloads['/' + name + '.tar.gz'] = data
    return payloads


@contextmanager
def archive_server(payloads):
    state = {'allow': False, 'requests': []}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            state['requests'].append(self.path)
            if not state['allow']:
                self.send_response(410)
                self.end_headers()
                return
            data = payloads.get(self.path)
            if data is None:
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *_args):
            pass

    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield server.server_port, state
    finally:
        server.shutdown()
        server.server_close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--repository-cache', type=Path, required=True)
    parser.add_argument('--bazel', type=Path, required=True)
    args = parser.parse_args()
    if hashlib.sha256(args.bazel.read_bytes()).hexdigest() != BAZEL_SHA256:
        raise ValueError('Expected pinned Bazel 9.2.0 binary')
    args.directory = args.directory.resolve()
    args.directory.mkdir(parents=True, exist_ok=False)
    cache = args.directory / 'archive-cache'
    copy_archive_cache(args.repository_cache, cache)
    payloads = archive_inputs(args.repository_cache)
    patch = Path(__file__).resolve().parents[2] / 'build/lazy-bats-toolchain.patch'
    report = {'scope': 'Toolchain metadata/runtime regression; fetched archives reused; no cold timing claim',
              'patch_sha256': hashlib.sha256(patch.read_bytes()).hexdigest(),
              'archive_sha256': {name: sha for name, (_, sha) in ARCHIVES.items()},
              'complete': False}
    try:
        with archive_server(payloads) as (port, state):
            config = args.directory / 'downloads.cfg'
            config.write_text(''.join(
                'rewrite github[.]com/bats-core/bats-' + name + '/archive/'
                + version.replace('.', '[.]') + '[.]tar[.]gz http://127.0.0.1:'
                + str(port) + '/' + name + '.tar.gz\n'
                for name, (version, _) in ARCHIVES.items()))

            def run(phase, source, command, target):
                state['requests'].clear()
                result = subprocess.run([
                    str(args.bazel.resolve()), '--ignore_all_rc_files', '--batch',
                    '--host_jvm_args=-Xmx2g', '--output_user_root=' + str(args.directory / ('user-' + phase)),
                    '--output_base=' + str(args.directory / ('output-' + phase)),
                    command, '--lockfile_mode=off', '--repository_cache=' + str(cache),
                    '--repo_contents_cache=', '--downloader_config=' + str(config),
                    '--jobs=2', '--spawn_strategy=linux-sandbox', '--remote_executor=', '--remote_cache=', target,
                ], cwd=source, capture_output=True, text=True, timeout=240)
                (args.directory / (phase + '.log')).write_text(result.stdout + '\n' + result.stderr)
                return result

            for phase in ['baseline', 'patched']:
                source = args.directory / phase
                source.mkdir()
                (source / 'MODULE.bazel').write_text(MODULE)
                (source / 'BUILD.bazel').write_text(BUILD)
                (source / 'probe.bzl').write_text(RULES)
                if phase == 'patched':
                    shutil.copy2(patch, source / 'lazy-bats.patch')
                    with (source / 'MODULE.bazel').open('a') as output:
                        output.write('single_version_override(module_name="bazel_lib", patch_strip=1, patches=["//:lazy-bats.patch"])\n')
                    with (source / 'BUILD.bazel').open('a') as output:
                        output.write('exports_files(["lazy-bats.patch"])\n')
                result = run(phase, source, 'cquery', '//:probe')
                if phase == 'baseline':
                    if not (result.returncode and state['requests'] and '410' in result.stderr):
                        raise ValueError('Baseline did not reproduce eager Bats download')
                    report['baseline_reproduced'] = True
                elif result.returncode or state['requests']:
                    raise ValueError('Patched registration failed or fetched unused Bats scripts')
                report[phase + '_requests'] = list(state['requests'])
            core_sha = ARCHIVES['core'][1]
            if (cache / 'content_addressable/sha256' / core_sha / 'file').exists():
                raise ValueError('Unused Bats archive unexpectedly present')
            report['unused_archive_absent'] = True
            build = source / 'BUILD.bazel'
            build.write_text('load("@bazel_lib//lib:bats.bzl", "bats_test")\n' + build.read_text()
                             + 'bats_test(name="smoke", srcs=["smoke.bats"], size="small", timeout="short")\n')
            (source / 'smoke.bats').write_text(SMOKE)
            state['allow'] = True
            result = run('runtime', source, 'test', '//:smoke')
            if result.returncode or set(state['requests']) != set(payloads):
                raise ValueError('Deferred Bats runtime/helper smoke failed')
            report.update(runtime_requests=list(state['requests']), runtime_smoke_passed=True, complete=True)
    finally:
        (args.directory / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
