"""Compare compiler archives on unchanged V8 commands; not a cold-build test."""

import argparse
import ast
import copy
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile
import time
import urllib.request

from tools.ci.chromium import ROOT
from tools.ci.compile.experiment import archive_outputs
from tools.ci.compile.local import local_compile_times, verify_ram_sandbox
from tools.ci.local_cold import BAZEL_SHA256, machine_limits


TARGET = '//tools/ci/compile/compiler_compare:linux-amd64'
SOURCES = tuple('v8/src/' + source for source in [
    'ic/ic.cc', 'runtime/runtime-function.cc', 'compiler/turboshaft/loop-unrolling-phase.cc',
    'compiler/turboshaft/store-store-elimination-phase.cc',
    'compiler/backend/x64/instruction-selector-x64.cc', 'builtins/builtins-array-gen.cc',
])
BASELINE_SHA256 = '2808ea0503af3656373fc141ddc7d082b53c7f858efd5245aed0241734257348'


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def replacement_index(index, archive, sha256):
    result = copy.deepcopy(index)
    key = result['latest_by_llvm_version']['23.1.2']
    original = result['releases'][key]['linux-amd64-musl']
    if original['sha256'] != BASELINE_SHA256:
        raise ValueError('Unexpected baseline compiler archive')
    result['releases'][key]['linux-amd64-musl'] = {'url': archive.as_uri(), 'sha256': sha256}
    return result


def configure_index(build, index, archive, sha256):
    (build.source / 'compiler-probe-index.json').write_text(json.dumps(
        replacement_index(index, archive, sha256)))
    with (build.source / 'MODULE.bazel').open('a') as module:
        module.write('\ncompiler_probe_llvm = use_extension("@llvm//extensions:llvm_toolchain_minimal.bzl", "llvm_toolchain_minimal")\n'
                     'compiler_probe_llvm.index(file = "//:compiler-probe-index.json")\n'
                     'use_repo(compiler_probe_llvm, "llvm-toolchain-minimal-darwin-amd64", "llvm-toolchain-minimal-darwin-arm64", '
                     '"llvm-toolchain-minimal-linux-amd64", "llvm-toolchain-minimal-linux-arm64", '
                     '"llvm-toolchain-minimal-windows-amd64", "llvm-toolchain-minimal-windows-arm64")\n')
    with (build.source / 'BUILD.bazel').open('a') as output:
        output.write('\nexports_files(["compiler-probe-index.json"])\n')


def verified_archive(path, sha256):
    path = path.resolve(strict=True)
    if (not re.fullmatch(r'[0-9a-f]{64}', sha256) or digest(path) != sha256
            or not path.name.endswith('.tar.zst')):
        raise ValueError('Compiler needs a verified .tar.zst archive')
    return path


def object_paths(rows, execution_root):
    files = [execution_root / item for row in rows for item in row]
    if len(files) != len(SOURCES) or len(set(files)) != len(files):
        raise ValueError('Expected one unique object per selected source')
    for file in files:
        if (not file.is_relative_to(execution_root / 'bazel-out') or '..' in file.parts
                or '/tools/ci/compile/compiler_compare/_objs/' not in file.as_posix()
                or file.suffix != '.o'):
            raise ValueError('Unexpected compiler output path')
    return files


def compiler_commands(graph):
    commands = {}
    for action in graph.get('actions', []):
        if action['mnemonic'] != 'CppCompile':
            continue
        parameters = {item['execPath']: item['arguments'] for item in action.get('paramFiles', [])}
        arguments = [value for item in action['arguments']
                     for value in (parameters[item[1:]] if item.startswith('@')
                                   and item[1:] in parameters else [item])]
        sources = [source for source in SOURCES if any(item.endswith(source) for item in arguments)]
        if len(sources) != 1 or sources[0] in commands:
            raise ValueError('Expected one compiler command per selected source')
        commands[sources[0]] = {'arguments': arguments,
                                'environment': sorted(action.get('environmentVariables', []),
                                                      key=lambda item: item['key'])}
    if set(commands) != set(SOURCES):
        raise ValueError('Selected compiler commands missing')
    return commands


class Build:
    def __init__(self, root, bazel, cache, sandbox, revision):
        self.root, self.source = root, root / 'source'
        self.source.mkdir(parents=True)
        with subprocess.Popen(['git', 'archive', '--format=tar', revision], cwd=ROOT,
                              stdout=subprocess.PIPE) as checkout:
            with tarfile.open(fileobj=checkout.stdout, mode='r|') as archive:
                archive.extractall(self.source, filter='data')
            if checkout.wait():
                raise ValueError('Compiler probe source checkout failed')
        self.startup = [str(bazel), '--nosystem_rc', '--nohome_rc', '--noworkspace_rc',
                        '--bazelrc=' + str(self.source / '.bazelrc'), '--host_jvm_args=-Xmx6g',
                        '--output_user_root=' + str(root / 'bazel-root'),
                        '--output_base=' + str(root / 'output-base')]
        self.flags = ['--config=browser', '--nodiscard_analysis_cache', '--track_incremental_state',
                      '--keep_state_after_build', '--jobs=8', '--local_resources=cpu=8',
                      '--local_resources=memory=10000', '--spawn_strategy=linux-sandbox',
                      '--sandbox_base=' + str(sandbox), '--remote_executor=', '--remote_cache=',
                      '--disk_cache=', '--repo_contents_cache=', '--remote_accept_cached=false',
                      '--noremote_upload_local_results', '--repository_cache=' + str(cache),
                      '--bes_backend=', '--bes_results_url=',
                      '--extra_execution_platforms=//platforms:buildbuddy_linux_amd64',
                      '--define=CHROMIUM_NATIVE_TOOLS=1',
                      '--extra_toolchains=@chromium//native/tool_configuration:native_linux_execution',
                      '--define=CHROMIUM_COMPILE_PROBE_SCAN=0']

    def query(self, operation, *arguments):
        result = subprocess.run([*self.startup, operation, *self.flags, *arguments],
                                cwd=self.source, capture_output=True, text=True)
        if result.returncode:
            print(result.stderr[-8000:], flush=True)
            raise ValueError('Compiler probe analysis failed: ' + operation)
        return result.stdout

    def analyze(self):
        query = 'kind("cc_library", filter("^//tools/ci/compile/compiler_compare:", deps(' + TARGET + ')))'
        expression = '[f.path for a in target.actions if a.mnemonic == "CppCompile" for f in a.outputs.to_list() if f.path.endswith(".o")]'
        rows = [ast.literal_eval(line) for line in self.query(
            'cquery', '--output=starlark', '--starlark:expr=' + expression, query).splitlines()]
        self.execution_root = Path(subprocess.check_output(
            [*self.startup, 'info', 'execution_root'], cwd=self.source, text=True).strip())
        self.objects = object_paths(rows, self.execution_root)
        commands = compiler_commands(json.loads(self.query(
            'aquery', '--output=jsonproto', '--include_param_files', 'mnemonic("CppCompile", ' + query + ')')))
        driver = ('external/llvm++llvm_toolchain_minimal+'
                  'llvm-toolchain-minimal-linux-amd64/bin/clang++')
        actual = {item['arguments'][0] for item in commands.values()}
        if actual != {driver}:
            raise ValueError('Expected indexed stage-0 compiler; got ' + ', '.join(sorted(actual)))
        self.compiler_binary_sha256 = digest(self.root / 'output-base' / driver)
        return commands

    def build(self, phase, measured):
        if measured:
            for file in self.objects:
                file.unlink()
        events, profile = self.root / (phase + '.events.json'), self.root / (phase + '.profile.gz')
        started = time.monotonic()
        with (self.root / (phase + '.log')).open('w') as output, subprocess.Popen([
                *self.startup, 'build', *self.flags, '--build_event_json_file=' + str(events),
                '--nobuild_event_json_file_path_conversion', '--profile=' + str(profile),
                '--record_full_profiler_data', TARGET], cwd=self.source,
                stdout=output, stderr=subprocess.STDOUT) as process:
            while True:
                try:
                    code = process.wait(timeout=30)
                    break
                except subprocess.TimeoutExpired:
                    print('Compiler comparison: ' + phase + ' running', flush=True)
        if code:
            print((self.root / (phase + '.log')).read_text(errors='replace')[-8000:], flush=True)
            raise ValueError('Compiler comparison failed: ' + phase)
        archives, metrics = archive_outputs(events, TARGET)
        row = {'wall_seconds': time.monotonic() - started, 'archives': archives,
               'build_metrics': metrics, 'objects': {
                   str(file.relative_to(self.execution_root)): digest(file) for file in self.objects}}
        if measured:
            row['selected_compiles'] = local_compile_times(profile, SOURCES)
            count = sum(int(item.get('actionsExecuted', 0))
                        for item in metrics.get('actionSummary', {}).get('actionData', [])
                        if item.get('mnemonic') == 'CppCompile')
            if count != len(SOURCES):
                raise ValueError('Measured passes require six actual compiles and no supporting recompiles')
        return row

    def shutdown(self):
        subprocess.run([*self.startup, 'shutdown'], cwd=self.source, check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--baseline-sha256')
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--candidate-sha256', required=True)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--sandbox-base', type=Path, required=True)
    parser.add_argument('--repository-cache', type=Path, required=True)
    parser.add_argument('--bazel', type=Path)
    parser.add_argument('--analyze-only', action='store_true')
    args = parser.parse_args()
    if bool(args.baseline) != bool(args.baseline_sha256):
        parser.error('--baseline and --baseline-sha256 must be supplied together')
    args.candidate = verified_archive(args.candidate, args.candidate_sha256)
    if args.baseline:
        args.baseline = verified_archive(args.baseline, args.baseline_sha256)
    args.directory = args.directory.resolve()
    args.sandbox_base = args.sandbox_base.resolve()
    args.repository_cache = args.repository_cache.resolve()
    if args.analyze_only:
        args.sandbox_base.mkdir(parents=True, exist_ok=True)
    else:
        verify_ram_sandbox(args.sandbox_base)
    args.directory.mkdir(parents=True, exist_ok=False)
    args.repository_cache.mkdir(parents=True, exist_ok=True)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    report = {'scope': 'Warm compiler comparison; supporting state retained; NOT cold-build proof',
              'revision': revision, 'machine': machine_limits(), 'complete': False, 'phases': {},
              'baseline_sha256': args.baseline_sha256 or BASELINE_SHA256, 'candidate_sha256': args.candidate_sha256}
    builds = {}
    try:
        with tempfile.TemporaryDirectory(prefix='chromium-compiler-compare-') as temporary:
            root = Path(temporary)
            bazel = args.bazel.resolve(strict=True) if args.bazel else root / 'bazel'
            if not args.bazel:
                with urllib.request.urlopen('https://github.com/bazelbuild/bazel/releases/download/'
                                            '9.2.0/bazel-9.2.0-linux-x86_64', timeout=120) as response, bazel.open('wb') as output:
                    shutil.copyfileobj(response, output)
                bazel.chmod(0o755)
            if digest(bazel) != BAZEL_SHA256:
                raise ValueError('Unexpected Bazel executable')
            try:
                for variant in ['baseline', 'candidate']:
                    builds[variant] = Build(root / variant, bazel, args.repository_cache,
                                            args.sandbox_base, revision)
                baseline = builds['baseline']
                commands = baseline.analyze()
                index = json.loads((baseline.root / 'output-base/external/llvm+/extensions/'
                                    'llvm_toolchain_minimal_index.json').read_text())
                candidate = builds['candidate']
                if args.baseline:
                    configure_index(baseline, index, args.baseline, args.baseline_sha256)
                    if baseline.analyze() != commands:
                        raise ValueError('Baseline replacement changed source commands or environment')
                configure_index(candidate, index, args.candidate, args.candidate_sha256)
                if candidate.analyze() != commands:
                    raise ValueError('Compiler comparison changed source commands or environment')
                report['compiler_commands_identical'] = True
                report['compiler_binary_sha256'] = {
                    name: build.compiler_binary_sha256 for name, build in builds.items()}
                if (args.candidate_sha256 != report['baseline_sha256']
                        and candidate.compiler_binary_sha256 == baseline.compiler_binary_sha256):
                    raise ValueError('Candidate archive does not change the compiler binary')
                if args.analyze_only:
                    report['build_skipped'] = True
                    return
                reference = None
                for phase, variant, measured in [
                    ('warmup-baseline', 'baseline', False), ('warmup-candidate', 'candidate', False),
                    ('baseline-1', 'baseline', True), ('candidate-1', 'candidate', True),
                    ('candidate-2', 'candidate', True), ('baseline-2', 'baseline', True),
                ]:
                    print('Compiler comparison: ' + phase, flush=True)
                    row = builds[variant].build(phase, measured)
                    report['phases'][phase] = row
                    current = row['archives'], row['objects']
                    if reference is None:
                        reference = current
                    if current != reference:
                        raise ValueError('Compiler object or archive bytes changed: ' + phase)
                    row['object_and_archive_bytes_match'] = True
                report['complete'] = True
            finally:
                for build in builds.values():
                    build.shutdown()
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        (args.directory / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps({key: value for key, value in report.items() if key != 'phases'}), flush=True)


if __name__ == '__main__':
    main()
