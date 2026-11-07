"""Measure local compiler concurrency without changing compiler commands."""

import argparse
import ast
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import urllib.request

from tools.ci.chromium import ROOT
from tools.ci.compile.experiment import archive_outputs, batch_sources
from tools.ci.compile.local import local_compile_times, verify_ram_sandbox
from tools.ci.local_cold import BAZEL_SHA256, machine_limits


TARGET = '//tools/ci/compile/local_throughput:linux-amd64'
SOURCES = (*batch_sources()[:256], batch_sources()[-1])


def object_paths(rows, execution_root):
    files = [execution_root / item for row in rows for item in row]
    if len(files) != len(SOURCES) or len(set(files)) != len(files):
        raise ValueError('Expected one unique object per selected source: '
                         + str(len(SOURCES)) + ' sources, ' + str(len(files))
                         + ' outputs, ' + str(len(set(files))) + ' unique outputs')
    for file in files:
        if (not file.is_relative_to(execution_root / 'bazel-out')
                or '/tools/ci/compile/local_throughput/_objs/' not in file.as_posix()
                or '..' in file.parts or file.suffix != '.o'):
            raise ValueError('Unexpected compiler output path: ' + str(file))
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--sandbox-base', type=Path, required=True)
    args = parser.parse_args()
    verify_ram_sandbox(args.sandbox_base)
    args.directory.mkdir(parents=True, exist_ok=False)
    machine = machine_limits()
    capacity = math.floor(machine['cpu_limit'])
    if capacity <= 16:
        raise ValueError('Runner has no additional CPU capacity beyond baseline 16')
    report = {'measurement': 'Warm supporting setup, selected compiles rerun; not cold proof',
              'machine': machine, 'memory_sample_interval_seconds': 5, 'source_count': len(SOURCES), 'complete': False, 'phases': {}}
    print(json.dumps(report), flush=True)
    cache = Path.home() / '.cache/chromium-strict-cold-downloads'
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='chromium-local-throughput-') as temporary:
        root = Path(temporary)
        bazel = root / 'bazel'
        with urllib.request.urlopen(
                'https://github.com/bazelbuild/bazel/releases/download/9.2.0/bazel-9.2.0-linux-x86_64',
                timeout=120) as response, bazel.open('wb') as output:
            shutil.copyfileobj(response, output)
        if hashlib.sha256(bazel.read_bytes()).hexdigest() != BAZEL_SHA256:
            raise ValueError('Bazel checksum mismatch')
        bazel.chmod(0o755)
        startup = [str(bazel), '--nosystem_rc', '--nohome_rc', '--noworkspace_rc',
                   '--bazelrc=' + str(ROOT / '.bazelrc'), '--host_jvm_args=-Xmx8g',
                   '--output_user_root=' + str(root / 'bazel-root'),
                   '--output_base=' + str(root / 'output-base')]
        flags = ['--config=browser', '--nodiscard_analysis_cache', '--track_incremental_state',
                 '--keep_state_after_build', '--spawn_strategy=linux-sandbox',
                 '--sandbox_base=' + str(args.sandbox_base), '--local_resources=memory=14000',
                 '--remote_executor=', '--remote_cache=', '--remote_accept_cached=false',
                 '--noremote_upload_local_results', '--disk_cache=', '--repo_contents_cache=',
                 '--repository_cache=' + str(cache), '--bes_backend=', '--bes_results_url=',
                 '--extra_execution_platforms=//platforms:buildbuddy_linux_amd64',
                 '--define=CHROMIUM_NATIVE_TOOLS=1',
                 '--extra_toolchains=@chromium//native/tool_configuration:native_linux_execution',
                 '--define=CHROMIUM_COMPILE_PROBE_SCAN=1']
        files = None
        reference = None
        try:
            print('Local throughput: analyze object inventory', flush=True)
            query = 'kind("cc_library", filter("^//tools/ci/compile/local_throughput:", deps(' + TARGET + ')))'
            expression = '[f.path for a in target.actions if a.mnemonic == "CppCompile" for f in a.outputs.to_list() if f.path.endswith(".o")]'
            result = subprocess.run([*startup, 'cquery', *flags, '--output=starlark',
                                     '--starlark:expr=' + expression, query],
                                    cwd=ROOT, capture_output=True, text=True)
            if result.returncode:
                print(result.stderr[-8000:], flush=True)
                raise ValueError('Compiler output inventory analysis failed')
            execution_root = Path(subprocess.check_output(
                [*startup, 'info', 'execution_root'], cwd=ROOT, text=True).strip())
            rows = [ast.literal_eval(line) for line in result.stdout.splitlines()]
            report['object_inventory'] = {'rows': len(rows), 'outputs_per_row': [len(row) for row in rows]}
            files = object_paths(rows, execution_root)
            for name, jobs in [('warmup', 16), ('baseline-1', 16), ('capacity-1', capacity),
                               ('capacity-2', capacity), ('baseline-2', 16)]:
                if name != 'warmup':
                    for file in files:
                        file.unlink()
                events = root / (name + '.events.json')
                profile = root / (name + '.profile.gz')
                command = [*startup, 'build', *flags, '--jobs=' + str(jobs),
                           '--local_resources=cpu=' + str(jobs),
                           '--build_event_json_file=' + str(events),
                           '--nobuild_event_json_file_path_conversion', '--profile=' + str(profile),
                           '--record_full_profiler_data', TARGET]
                print('Local throughput: ' + name + ', jobs=' + str(jobs), flush=True)
                started = time.monotonic()
                available = []
                next_progress = started + 30
                log = root / (name + '.log')
                with log.open('w') as output, subprocess.Popen(
                        command, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT) as process:
                    while True:
                        memory = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
                        available.append(int(memory['MemAvailable'].split()[0]) * 1024)
                        try:
                            code = process.wait(timeout=5)
                            break
                        except subprocess.TimeoutExpired:
                            if time.monotonic() >= next_progress:
                                next_progress = time.monotonic() + 30
                                with log.open('rb') as stream:
                                    stream.seek(max(0, log.stat().st_size - 2048))
                                    progress = stream.read().decode(errors='replace').splitlines()
                                print(name + ': ' + next((line for line in reversed(progress)
                                      if line.startswith('[')), 'build running'), flush=True)
                if code:
                    print(log.read_text(errors='replace')[-8000:], flush=True)
                    raise ValueError('Local throughput build failed: ' + name)
                archives, metrics = archive_outputs(events, TARGET)
                row = {'wall_seconds': time.monotonic() - started, 'jobs': jobs,
                       'minimum_sampled_available_memory_bytes': min(available), 'archives': archives,
                       'build_metrics': metrics}
                report['phases'][name] = row
                if name != 'warmup':
                    row['selected_compiles'] = local_compile_times(profile, SOURCES)
                    executed = sum(int(item.get('actionsExecuted', 0))
                                   for item in metrics.get('actionSummary', {}).get('actionData', [])
                                   if item.get('mnemonic') == 'CppCompile')
                    if executed != len(SOURCES):
                        raise ValueError('Selected compiles must execute without supporting recompiles')
                hashes = {str(file.relative_to(execution_root)): hashlib.sha256(file.read_bytes()).hexdigest() for file in files}
                current = archives, hashes
                if reference is None:
                    reference = current
                if current != reference:
                    raise ValueError('Compiler object or archive bytes changed')
                row['object_bytes_match'] = True
            report['complete'] = True
        except Exception as error:
            report['error'] = str(error)
            raise
        finally:
            subprocess.run([*startup, 'shutdown'], cwd=ROOT, check=False, stdout=subprocess.DEVNULL)
            (args.directory / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
            print(json.dumps({key: value for key, value in report.items() if key != 'phases'}), flush=True)


if __name__ == '__main__':
    main()
