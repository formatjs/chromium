"""Profile representative V8 compilers without changing optimization settings."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import urllib.request

from tools.ci.chromium import ROOT
from tools.ci.compile.experiment import archive_outputs, compiler_pattern
from tools.ci.compile.local import local_compile_times, verify_ram_sandbox
from tools.ci.local_cold import BAZEL_SHA256, machine_limits


TARGET = '//tools/ci/compile/clang_trace:v8-linux-amd64'
SOURCES = tuple('v8/src/' + source for source in [
    'ic/ic.cc', 'runtime/runtime-function.cc', 'compiler/turboshaft/loop-unrolling-phase.cc',
    'compiler/turboshaft/store-store-elimination-phase.cc',
    'compiler/backend/x64/instruction-selector-x64.cc', 'builtins/builtins-array-gen.cc',
])


def compiler_trace_summary(path):
    events = json.loads(path.read_text())['traceEvents']
    totals = {event['name'].removeprefix('Total '): event['dur'] / 1e6
              for event in events if event.get('ph') == 'X'
              and event.get('name', '').startswith('Total ') and event.get('dur', 0) > 0}
    if totals.get('ExecuteCompiler', 0) <= 0:
        raise ValueError('Complete Clang compiler total missing')
    return {'compiler_seconds': totals['ExecuteCompiler'],
            'frontend_seconds': totals.get('Frontend'), 'backend_seconds': totals.get('Backend'),
            'totals_seconds': totals, 'nested_totals_are_not_additive': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--sandbox-base', type=Path, required=True)
    args = parser.parse_args()
    verify_ram_sandbox(args.sandbox_base)
    args.directory.mkdir(parents=True, exist_ok=False)
    report = {'measurement': 'Instrumented selected compilers with warm support; not cold-build proof',
              'machine': machine_limits(), 'complete': False, 'phases': {}}
    with tempfile.TemporaryDirectory(prefix='chromium-clang-profile-') as temporary:
        root = Path(temporary)
        try:
            bazel = root / 'bazel-9.2.0'
            with urllib.request.urlopen(
                    'https://github.com/bazelbuild/bazel/releases/download/9.2.0/bazel-9.2.0-linux-x86_64',
                    timeout=120) as response, bazel.open('wb') as output:
                shutil.copyfileobj(response, output)
            if hashlib.sha256(bazel.read_bytes()).hexdigest() != BAZEL_SHA256:
                raise ValueError('Bazel release checksum mismatch')
            bazel.chmod(0o755)
            for phase in ['warmup', 'trace']:
                print('Clang profile phase: ' + phase, flush=True)
                events, profile = root / (phase + '.events.json'), root / (phase + '.profile.gz')
                command = [str(bazel), '--nosystem_rc', '--nohome_rc', '--noworkspace_rc',
                           '--bazelrc=' + str(ROOT / '.bazelrc'), '--batch', '--host_jvm_args=-Xmx8g',
                           '--output_user_root=' + str(root / 'bazel-root'), '--output_base=' + str(root / 'output-base'),
                           'build', '--config=browser', '--jobs=8', '--local_resources=cpu=8',
                           '--local_resources=memory=16000', '--spawn_strategy=linux-sandbox',
                           '--sandbox_base=' + str(args.sandbox_base), '--remote_executor=', '--remote_cache=',
                           '--remote_accept_cached=false', '--noremote_upload_local_results', '--disk_cache=',
                           '--repo_contents_cache=', '--repository_cache=' + str(root / 'fetch-cache'),
                           '--bes_backend=', '--bes_results_url=',
                           '--extra_execution_platforms=//platforms:buildbuddy_linux_amd64',
                           '--define=CHROMIUM_NATIVE_TOOLS=1',
                           '--extra_toolchains=@chromium//native/tool_configuration:native_linux_execution',
                           '--define=CHROMIUM_COMPILE_PROBE_SCAN=0',
                           '--build_event_json_file=' + str(events), '--nobuild_event_json_file_path_conversion',
                           '--profile=' + str(profile), '--record_full_profiler_data']
                if phase == 'trace':
                    command += ['--sandbox_debug',
                                '--per_file_copt=' + compiler_pattern(SOURCES) + '@-ftime-trace',
                                '--per_file_copt=' + compiler_pattern(SOURCES) + '@-ftime-trace-granularity=500']
                command.append(TARGET)
                started = time.monotonic()
                log = root / (phase + '.log')
                with log.open('w') as output, subprocess.Popen(
                        command, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT) as process:
                    while True:
                        try:
                            code = process.wait(timeout=30)
                            break
                        except subprocess.TimeoutExpired:
                            print('Clang profile ' + phase + ' running', flush=True)
                if code:
                    print(log.read_text(errors='replace')[-8000:], flush=True)
                    raise ValueError('Clang profile build failed: ' + phase)
                hashes, metrics = archive_outputs(events, TARGET)
                report['phases'][phase] = {'wall_seconds': time.monotonic() - started,
                                          'archives': hashes, 'build_metrics': metrics}
                if phase == 'trace':
                    report['phases'][phase]['selected_compiles'] = local_compile_times(profile, SOURCES)
            report['instrumented_archives_identical'] = (
                report['phases']['warmup']['archives'] == report['phases']['trace']['archives'])
            report['compiler_traces'] = {}
            paths = [path for path in args.sandbox_base.rglob('*.json') if '/_objs/' in path.as_posix()]
            for source in SOURCES:
                stem = Path(source).stem
                names = {stem + suffix for suffix in ['.json', '.pic.json', '.o.json', '.pic.o.json']}
                matches = [path for path in paths if path.name in names]
                if len(matches) != 1:
                    raise ValueError('Expected one retained Clang trace for ' + source)
                report['compiler_traces'][source] = compiler_trace_summary(matches[0])
                shutil.copyfile(matches[0], args.directory / (stem + '.json'))
            if not report['instrumented_archives_identical']:
                raise ValueError('Clang tracing changed archive bytes; inspect before accepting comparison')
            report['complete'] = True
        except Exception as error:
            report['error'] = str(error)
            raise
        finally:
            (args.directory / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
            print(json.dumps({key: report[key] for key in report if key != 'phases'}), flush=True)


if __name__ == '__main__':
    main()
