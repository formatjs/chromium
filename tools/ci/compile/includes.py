"""Run the captured-include pilot with byte and compiler-argument checks."""

import argparse
import ast
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import urllib.request

from tools.ci.chromium import ROOT
from tools.ci.local_cold import BAZEL_SHA256


def download(path, url, digest):
    with urllib.request.urlopen(url, timeout=120) as response, path.open('wb') as output:
        shutil.copyfileobj(response, output)
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise ValueError('Tool checksum mismatch: ' + path.name)
    path.chmod(0o755)


def compiler_search_paths(arguments):
    if not arguments or any(arg.startswith('@') for arg in arguments):
        raise ValueError('Expanded compiler arguments required')
    paths, position = [], 0
    while position < len(arguments):
        argument = arguments[position]
        for flag in ('-isystem', '-iquote', '-I'):
            if argument.startswith(flag):
                if argument == flag:
                    position += 1
                    if position == len(arguments):
                        raise ValueError('Compiler search path missing: ' + flag)
                    path = arguments[position]
                else:
                    path = argument[len(flag):]
                paths.append({'flag': flag, 'path': path})
                break
        position += 1
    return paths


def compiler_search_count(arguments):
    return len(compiler_search_paths(arguments))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--sandbox-base', type=Path, required=True)
    parser.add_argument('--arguments-only', action='store_true')
    args = parser.parse_args()
    args.directory.mkdir(parents=True, exist_ok=False)
    cache = Path.home() / '.cache/chromium-strict-cold-downloads'
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='chromium-private-includes-') as temporary:
        root = Path(temporary)
        trial = root / 'trial'
        report = {'measurement': 'Warm compiler pilot; not cold-build proof', 'complete': False}
        try:
            bazel, bb = root / 'bazel', root / 'bb'
            download(bazel, 'https://github.com/bazelbuild/bazel/releases/download/9.2.0/bazel-9.2.0-linux-x86_64', BAZEL_SHA256)
            if args.arguments_only:
                trial.mkdir()
                report.update(measurement='Analysis only; no compiler executions or timing claim',
                              compile_trial_skipped=True)
            else:
                download(bb, 'https://github.com/buildbuddy-io/bazel/releases/download/5.0.500/bazel-5.0.500-linux-x86_64',
                         'f8a188913203f23961a61f1c5eb64b0eef65cf24e0014ec074b5598af4fbc68a')
                command = [sys.executable, '-m', 'tools.ci.compile.local', '--comparison', 'local-includes',
                           '--directory', str(trial), '--repository-cache', str(cache),
                           '--sandbox-base', str(args.sandbox_base), '--jobs', '8',
                           '--bazel', str(bazel), '--bb', str(bb)]
                with subprocess.Popen(command, cwd=ROOT) as process:
                    while True:
                        try:
                            code = process.wait(timeout=30)
                            break
                        except subprocess.TimeoutExpired:
                            print('Compiler include pilot running', flush=True)
                if (trial / 'report.json').exists():
                    report.update(json.loads((trial / 'report.json').read_text()))
                if code:
                    for log in sorted(trial.glob('*.log'), key=lambda p: p.stat().st_mtime)[-1:]:
                        print(log.read_text(errors='replace')[-8000:], flush=True)
                    raise ValueError('Compiler include pilot failed')

            # Query after measurements so diagnostics cannot affect their timing.
            counts = {}
            for enabled in [0, 1]:
                command = [str(bazel), '--nosystem_rc', '--nohome_rc', '--noworkspace_rc',
                           '--bazelrc=' + str(ROOT / '.bazelrc'), '--batch', '--host_jvm_args=-Xmx12g',
                           '--output_user_root=' + str(trial / 'bazel-root'),
                           '--output_base=' + str(trial / 'output-base'),
                           '--install_base=' + str(trial / 'install-base'), 'cquery', '--config=browser',
                           '--nodiscard_analysis_cache', '--track_incremental_state', '--keep_state_after_build',
                           '--extra_execution_platforms=//platforms:buildbuddy_linux_amd64',
                           '--remote_executor=', '--remote_cache=', '--disk_cache=', '--repo_contents_cache=',
                           '--repository_cache=' + str(cache), '--bes_backend=', '--bes_results_url=',
                           '--define=CHROMIUM_COMPILE_PROBE_SCAN=1', '--define=CHROMIUM_LOCAL_INCLUDES=' + str(enabled),
                           '--output=starlark',
                           '--starlark:expr=[list(a.argv) for a in target.actions if a.mnemonic == "CppCompile"]',
                           '//tools/ci/compile/local:gin']
                graph = root / ('arguments-' + str(enabled) + '.json')
                with graph.open('w') as output:
                    subprocess.run(command, cwd=ROOT, stdout=output, check=True)
                # Native Action.argv expands response files; aquery may expose only @file.
                rows = ast.literal_eval(graph.read_text())
                report.setdefault('first_compile_search_paths', {})[str(enabled)] = (
                    compiler_search_paths(rows[0]) if rows else [])
                report.setdefault('argument_rows', {})[str(enabled)] = [
                    {'argument_count': len(arguments),
                     'response_file_count': sum(arg.startswith('@') for arg in arguments)}
                    for arguments in rows]
                values = []
                for arguments in rows:
                    values.append(compiler_search_count(arguments))
                counts[str(enabled)] = sorted(values)
                report['header_search_entries'] = counts
            if (len(counts['0']) != 4 or len(counts['1']) != 4
                    or not all(0 < new < old for old, new in zip(counts['0'], counts['1']))):
                raise ValueError('Compiler search lists did not shrink for all four Gin compiles')
            report.update(header_search_entries=counts, complete=True)
        except Exception as error:
            report['error'] = str(error)
            raise
        finally:
            (args.directory / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
            print(json.dumps({key: value for key, value in report.items()
                              if key != 'first_compile_search_paths'}), flush=True)


if __name__ == '__main__':
    main()
