"""Run the local cold-build protocol inside a BuildBuddy workflow runner."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

from tools.ci.local_cold import BAZEL_SHA256, BAZEL_URL, machine_limits
from tools.ci.profile_buildbuddy import trace_summary


def main():
    started = time.monotonic()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--jobs', type=int, default=16)
    parser.add_argument('--native-tools', action='store_true')
    parser.add_argument('--project-pch', action='store_true', help='Opt into validated V8, Content and module PCH candidates')
    parser.add_argument('--blink-pch', action='store_true')
    parser.add_argument('--binding-workers', type=int, choices=[1, 2, 4], default=1)
    parser.add_argument('--trained-compiler', action='store_true')
    parser.add_argument('--compiler-profile', choices=['cxx', 'chromium'], default='cxx')
    args = parser.parse_args()
    if args.compiler_profile != 'cxx' and not args.trained_compiler:
        parser.error('--compiler-profile requires --trained-compiler')
    if args.project_pch and not args.blink_pch:
        parser.error('--project-pch requires --blink-pch')
    if args.blink_pch and not args.native_tools:
        parser.error('--blink-pch requires --native-tools')
    destination = args.directory.resolve()
    destination.mkdir(parents=True, exist_ok=False)
    profile = destination / 'cold-profile.json.gz'
    # Workflow snapshots may retain this download cache. Nothing else is reused.
    cache = Path.home() / '.cache/chromium-strict-cold-downloads'
    cache.mkdir(parents=True, exist_ok=True)
    report = {'revision': args.revision, 'platform': 'linux-amd64',
              'machine': machine_limits(), 'cold_result_verified': False,
              'blink_pch_requested': args.blink_pch, 'project_pch_requested': args.project_pch,
              'trained_compiler': args.trained_compiler, 'compiler_profile': args.compiler_profile, 'binding_workers': args.binding_workers,
              'profile_format': 'gzip; standard Bazel slim trace; full BEP and execution log',
              'profile_complete_verified': False,
              'under_one_hour': False, 'runner': 'BuildBuddy workflow; RBE disabled',
              'os_page_cache': 'uncontrolled; workflow VM may be restored from a snapshot'}
    print(json.dumps(report), flush=True)
    with tempfile.TemporaryDirectory(prefix='chromium-bb-strict-cold-') as temporary:
        root = Path(temporary)
        trial = root / 'trial'
        try:
            compiler = None
            if args.trained_compiler:
                from tools.ci.compiler_archive import ARCHIVES, ensure_archive
                spec = ARCHIVES[args.compiler_profile]
                compiler = cache / 'compiler-archives' / spec['sha256'] / spec['name']
                fetched = time.monotonic()
                report['compiler_dependency_fetch'] = ensure_archive(compiler, args.compiler_profile)
                report['compiler_dependency_fetch']['seconds'] = time.monotonic() - fetched
            # Never invoke the workflow's Bazel wrapper or its injected RC files.
            bazel = root / 'bazel-9.2.0'
            request = urllib.request.Request(BAZEL_URL)
            with urllib.request.urlopen(request, timeout=120) as response, bazel.open('wb') as output:
                shutil.copyfileobj(response, output)
            if hashlib.sha256(bazel.read_bytes()).hexdigest() != BAZEL_SHA256:
                raise ValueError('Bazel release checksum mismatch')
            bazel.chmod(0o755)
            report['bootstrap_seconds'] = time.monotonic() - started
            command = [sys.executable, '-m', 'tools.ci.compile.private_ram', '--size-gib', '8', '--',
                       sys.executable, '-m', 'tools.ci.local_cold', '--directory', str(trial),
                       '--repository-cache', str(cache), '--revision', args.revision,
                       '--bazel', str(bazel), '--jobs', str(args.jobs),
                       '--heap-gib', '8', '--action-memory-mb', '14000', '--sandbox-base', '{sandbox}',
                       '--profile', str(profile),
                       '--max-seconds', '0']
            if compiler is not None:
                command.extend(['--compiler-archive', str(compiler), '--compiler-profile', args.compiler_profile])
            if args.binding_workers != 1:
                command.extend(['--binding-workers', str(args.binding_workers)])
            if args.native_tools:
                command.append('--native-tools')
            if args.blink_pch:
                command.append('--blink-pch')
            if args.project_pch:
                command.append('--project-pch')
            with subprocess.Popen(command) as process:
                while True:
                    try:
                        code = process.wait(timeout=30)
                        break
                    except subprocess.TimeoutExpired:
                        progress = trial / 'progress.json'
                        if progress.exists():
                            print(progress.read_text().strip(), flush=True)
                        log = trial / 'build.log'
                        if log.exists():
                            with log.open('rb') as stream:
                                stream.seek(max(0, log.stat().st_size - 2048))
                                lines = stream.read().decode(errors='replace').splitlines()
                            print('\n'.join(lines[-4:]), flush=True)
            report['benchmark_exit_code'] = code
            result = trial / 'cold-build.json'
            if result.exists():
                report.update(json.loads(result.read_text()))
            for artifact in (trial / 'artifacts').glob('*'):
                shutil.copyfile(artifact, destination / artifact.name)
            # Count the second artifact copy required for BB handoff as well.
            report['protocol_elapsed_seconds'] = report.get('elapsed_seconds')
            report['elapsed_seconds'] = time.monotonic() - started
            report['under_one_hour'] = bool(report['cold_result_verified']
                                           and report['elapsed_seconds'] < 3600)
            if not report['cold_result_verified']:
                log = trial / 'build.log'
                if log.exists():
                    with log.open('rb') as stream:
                        stream.seek(max(0, log.stat().st_size - 12000))
                        print(stream.read().decode(errors='replace'), flush=True)
            if profile.exists():
                try:
                    summary = trace_summary(profile, allow_partial=not report['cold_result_verified'])
                    report['profile_bytes'] = profile.stat().st_size
                    report['profile_complete_verified'] = bool(summary['trace_complete'] and summary['event_count']
                        and sum(row['compile_spans'] for row in summary['compiler_work'].values()) > 0)
                    (destination / 'trace-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
                except (ValueError, EOFError) as error:
                    report['profile_error'] = str(error)
        finally:
            report['elapsed_seconds'] = time.monotonic() - started
            report['under_one_hour'] = bool(report['cold_result_verified'] and report['profile_complete_verified']
                                           and report['elapsed_seconds'] < 3600)
            # Raw BEP/commands stay private; BB retains the streaming profile.
            (destination / 'cold-build.json').write_text(json.dumps(report, indent=2) + '\n')
            print(json.dumps(report), flush=True)
    return 0 if report['under_one_hour'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
