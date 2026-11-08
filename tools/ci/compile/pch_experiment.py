"""Compare declared PCH against the same Blink cohort at fixed resources."""

import argparse
import ast
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import time
import urllib.request

from tools.ci.chromium import ROOT
from tools.ci.compile.experiment import archive_outputs, batch_sources
from tools.ci.compile.local import local_compile_times, verify_ram_sandbox
from tools.ci.compiler_archive import configure_compiler, verify_compiler
from tools.ci.local_cold import BAZEL_SHA256, machine_limits

SOURCES = batch_sources()[:256]
PACKAGE = 'tools/ci/compile/pch'
OWNER = 'blink_pch_compile_probe'
TARGETS = {'baseline': '//' + PACKAGE + ':baseline-linux-amd64',
           'pch': '//' + PACKAGE + ':linux-amd64'}


def owned_objects(rows, execution_root, owner):
    """Only delete unique, inventoried objects owned by this probe."""
    prefix = '/' + PACKAGE + '/_objs/' + owner + '/'
    files = [execution_root / item for row in rows for item in row]
    if len(files) != len(SOURCES) or len(set(files)) != len(files):
        raise ValueError('Expected one unique object per selected source')
    result = {}
    for file in files:
        if (not file.is_relative_to(execution_root / 'bazel-out')
                or prefix not in file.as_posix() or '..' in file.parts or file.suffix != '.o'):
            raise ValueError('Compiler output outside probe inventory')
        key = file.as_posix().split(prefix, 1)[1]
        if key in result:
            raise ValueError('Ambiguous compiler output name')
        result[key] = file
    return result


def normalized_commands(rows, pch_path=None):
    """Preserve source, flags, include order and environment across variants."""
    result = {}
    for original, environment in rows:
        arguments = list(original)
        if '-c' not in arguments or '-o' not in arguments:
            raise ValueError('Expanded C++ compile command required')
        source = arguments[arguments.index('-c') + 1]
        if pch_path is None:
            if '-include-pch' in arguments:
                raise ValueError('Unexpected PCH in baseline command')
        else:
            if arguments.count('-include-pch') != 1:
                raise ValueError('Expected one explicit PCH input')
            index = arguments.index('-include-pch')
            if arguments[index + 1] != pch_path:
                raise ValueError('Compiler uses a different PCH')
            del arguments[index:index + 2]
        for option in ['-o', '-MF', '-MT']:
            if option in arguments:
                arguments[arguments.index(option) + 1] = '<output>'
        arguments = ['-frandom-seed=<output>' if value.startswith('-frandom-seed=') else value
                     for value in arguments]
        if source in result:
            raise ValueError('Duplicate source command')
        result[source] = arguments, environment
    if len(result) != len(SOURCES):
        raise ValueError('Incomplete compiler command inventory')
    return result


def verify_command_compilers(commands, output_base, expected):
    """Verify compiler inputs before Bazel materializes its execution root."""
    for compiler_path in {arguments[0] for arguments, _ in commands.values()}:
        relative = Path(compiler_path)
        if relative.is_absolute() or relative.parts[:1] != ('external',) or '..' in relative.parts:
            raise ValueError('Expected fetched hermetic compiler')
        actual = hashlib.sha256((output_base / relative).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError('Compile command uses a different compiler binary')


def query(startup, flags, source, expression, target):
    result = subprocess.run([*startup, 'cquery', *flags, '--output=starlark',
                             '--starlark:expr=' + expression, target],
                            cwd=source, capture_output=True, text=True)
    if result.returncode:
        print(result.stderr[-6000:], flush=True)
        raise ValueError('PCH probe analysis failed')
    return [ast.literal_eval(line) for line in result.stdout.splitlines()]


def measure(startup, flags, source, name, target, directory):
    events = directory / (name + '.events.json')
    profile = directory / (name + '.profile.gz')
    log = directory / (name + '.log')
    command = [*startup, 'build', *flags, '--build_event_json_file=' + str(events),
               '--nobuild_event_json_file_path_conversion', '--profile=' + str(profile),
               '--record_full_profiler_data', '--noslim_profile', target]
    started = time.monotonic()
    available = []
    next_progress = started + 30
    with log.open('w') as output, subprocess.Popen(
            command, cwd=source, stdout=output, stderr=subprocess.STDOUT) as process:
        while True:
            memory = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
            available.append(int(memory['MemAvailable'].split()[0]) * 1024)
            try:
                code = process.wait(timeout=5)
                break
            except subprocess.TimeoutExpired:
                if time.monotonic() >= next_progress:
                    next_progress = time.monotonic() + 30
                    print(name + ': build running, elapsed=' + str(round(time.monotonic() - started)), flush=True)
    elapsed = time.monotonic() - started
    if code:
        print(log.read_text(errors='replace')[-6000:], flush=True)
        raise ValueError('PCH probe build failed: ' + name)
    archives, metrics = archive_outputs(events, target)
    if len(archives) != 1:
        raise ValueError('Expected one cohort archive')
    return {'wall_seconds': elapsed, 'minimum_sampled_available_memory_bytes': min(available),
            'archive_sha256': next(iter(archives.values())), 'build_metrics': metrics}, profile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--sandbox-base', type=Path, required=True)
    parser.add_argument('--compiler-archive', type=Path, required=True)
    args = parser.parse_args()
    verify_ram_sandbox(args.sandbox_base)
    args.directory.mkdir(parents=True, exist_ok=False)
    machine = machine_limits()
    capacity = math.floor(machine['cpu_limit'])
    if capacity < 1:
        raise ValueError('Runner needs a positive CPU budget')
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    report = {'measurement': 'Warm support; selected compiles and candidate PCH rebuilt; not cold proof',
              'revision': revision, 'machine': machine, 'jobs': capacity, 'cpu_budget': capacity,
              'memory_sample_interval_seconds': 5, 'source_count': len(SOURCES),
              'complete': False, 'phases': {}}
    cache = Path.home() / '.cache/chromium-strict-cold-downloads'
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='chromium-pch-experiment-') as temporary:
        root = Path(temporary)
        source = root / 'source'
        source.mkdir()
        with subprocess.Popen(['git', 'archive', '--format=tar', revision], cwd=ROOT, stdout=subprocess.PIPE) as checkout:
            with tarfile.open(fileobj=checkout.stdout, mode='r|') as archive:
                archive.extractall(source, filter='data')
            if checkout.wait():
                raise ValueError('Probe source checkout failed')
        report['compiler_dependency'] = configure_compiler(source, args.compiler_archive)
        bazel = root / 'bazel'
        with urllib.request.urlopen(
                'https://github.com/bazelbuild/bazel/releases/download/9.2.0/bazel-9.2.0-linux-x86_64',
                timeout=120) as response, bazel.open('wb') as output:
            shutil.copyfileobj(response, output)
        if hashlib.sha256(bazel.read_bytes()).hexdigest() != BAZEL_SHA256:
            raise ValueError('Bazel checksum mismatch')
        bazel.chmod(0o755)
        startup = [str(bazel), '--nosystem_rc', '--nohome_rc', '--noworkspace_rc',
                   '--bazelrc=' + str(source / '.bazelrc'), '--host_jvm_args=-Xmx8g',
                   '--output_user_root=' + str(root / 'bazel-root'),
                   '--output_base=' + str(root / 'output-base'), '--install_base=' + str(root / 'install-base')]
        flags = ['--config=browser', '--nodiscard_analysis_cache', '--track_incremental_state',
                 '--keep_state_after_build', '--spawn_strategy=linux-sandbox',
                 '--sandbox_base=' + str(args.sandbox_base), '--local_resources=memory=14000',
                 '--jobs=' + str(capacity), '--local_resources=cpu=' + str(capacity),
                 '--remote_executor=', '--remote_cache=', '--remote_accept_cached=false',
                 '--noremote_upload_local_results', '--disk_cache=', '--repo_contents_cache=',
                 '--repository_cache=' + str(cache), '--bes_backend=', '--bes_results_url=',
                 '--extra_execution_platforms=//platforms:buildbuddy_linux_amd64',
                 '--define=CHROMIUM_NATIVE_TOOLS=1',
                 '--extra_toolchains=@chromium//native/tool_configuration:native_linux_execution',
                 '--define=CHROMIUM_COMPILE_PROBE_SCAN=1', '--define=CHROMIUM_BINDINGS_WORKERS=4']
        try:
            execution_root = Path(subprocess.check_output(
                [*startup, 'info', 'execution_root'], cwd=source, text=True).strip())
            files = {}
            commands = {}
            pch_target = '//' + PACKAGE + ':' + OWNER + '_pch'
            pch_rows = query(startup, flags, source, '[f.path for f in target.files.to_list()]', pch_target)
            pch_relative, = pch_rows[0]
            pch = execution_root / pch_relative
            if ('..' in pch.parts or not pch.is_relative_to(execution_root / 'bazel-out')
                    or '/' + PACKAGE + '/' not in pch.as_posix() or pch.suffix != '.pch'):
                raise ValueError('PCH output outside probe inventory')
            for variant in TARGETS:
                owner = OWNER + ('_baseline' if variant == 'baseline' else '')
                target = '//' + PACKAGE + ':' + owner
                rows = query(startup, flags, source,
                             '[f.path for a in target.actions if a.mnemonic == "CppCompile" for f in a.outputs.to_list() if f.path.endswith(".o")]', target)
                files[variant] = owned_objects(rows, execution_root, owner)
                rows, = query(startup, flags, source,
                              '[(a.argv, a.env) for a in target.actions if a.mnemonic == "CppCompile"]', target)
                commands[variant] = normalized_commands(rows, pch_relative if variant == 'pch' else None)
            if commands['baseline'] != commands['pch']:
                raise ValueError('PCH consumer changes other compiler flags or environment')
            report['consumer_commands_equivalent'] = True
            report['compiler_context_sha256'] = hashlib.sha256(json.dumps(commands['baseline'], sort_keys=True).encode()).hexdigest()
            report['actual_binary_sha256'] = verify_compiler(root / 'output-base')
            verify_command_compilers(commands['baseline'], root / 'output-base', report['actual_binary_sha256'])
            reference = None
            for name, variant in [('warmup-baseline', 'baseline'), ('warmup-pch', 'pch'),
                                  ('baseline-1', 'baseline'), ('pch-1', 'pch'),
                                  ('pch-2', 'pch'), ('baseline-2', 'baseline')]:
                if not name.startswith('warmup'):
                    for file in files[variant].values():
                        file.unlink()
                    if variant == 'pch':
                        pch.unlink()
                print('PCH experiment: ' + name, flush=True)
                row, profile = measure(startup, flags, source, name, TARGETS[variant], root)
                report['phases'][name] = row
                if not name.startswith('warmup'):
                    row['selected_compiles'] = local_compile_times(profile, SOURCES)
                    data = row['build_metrics'].get('actionSummary', {}).get('actionData', [])
                    counts = {item['mnemonic']: int(item.get('actionsExecuted', 0)) for item in data}
                    if counts.get('CppCompile') != len(SOURCES) or counts.get('ChromiumPython', 0):
                        raise ValueError('Measured pass recompiles supporting actions')
                    if counts.get('ChromiumPch', 0) != (1 if variant == 'pch' else 0):
                        raise ValueError('PCH must rebuild exactly once in each candidate pass')
                hashes = {key: hashlib.sha256(file.read_bytes()).hexdigest() for key, file in files[variant].items()}
                current = row['archive_sha256'], hashes
                if reference is None:
                    reference = current
                if current != reference:
                    raise ValueError('PCH changes compiler objects or archive bytes')
                row['object_and_archive_bytes_match'] = True
                print(json.dumps({'phase': name, 'wall_seconds': row['wall_seconds'],
                                  'object_and_archive_bytes_match': True}), flush=True)
            report['complete'] = True
        except Exception as error:
            report['error'] = str(error)
            raise
        finally:
            subprocess.run([*startup, 'shutdown'], cwd=source, check=False, stdout=subprocess.DEVNULL)
            (args.directory / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
            print(json.dumps({key: value for key, value in report.items() if key != 'phases'}), flush=True)


if __name__ == '__main__':
    main()
