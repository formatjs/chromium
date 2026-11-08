"""Compare declared Blink compiler variants at fixed resources."""

import argparse
import ast
import hashlib
import json
import math
import posixpath
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
from tools.ci.compile.pch_reproducibility import verify as verify_pch_reproducibility, verify_producer_options
from tools.ci.compiler_archive import configure_compiler, verify_compiler
from tools.ci.local_cold import BAZEL_SHA256, BAZEL_URL, machine_limits

SOURCES = batch_sources()[:256]
PACKAGE = 'tools/ci/compile/pch'
OWNER = 'blink_pch_compile_probe'
# Original frozen cohort archive, before include/PCH experiments.
ARCHIVE_SHA256 = '4a346e0ea2f9d63adfe21ceade07f671006b4653476f487c1f92aeac5ee2fb90'
TARGETS = {'baseline': '//' + PACKAGE + ':baseline-linux-amd64',
           'pch': '//' + PACKAGE + ':linux-amd64'}


def owned_objects(rows, execution_root, owner, split=False, package=PACKAGE, groups=(), expected_count=None):
    """Only delete unique, inventoried objects owned by this probe."""
    prefixes = ['/' + package + '/_objs/' + owner + suffix + '/'
                for suffix in (tuple('_' + group for group in groups) if groups else
                               ('_pch', '_plain') if split else ('',))]
    files = [execution_root / item for row in rows for item in row]
    count = len(SOURCES) if expected_count is None else expected_count
    if len(files) != count or len(set(files)) != len(files):
        raise ValueError('Expected one unique object per selected source')
    result = {}
    for file in files:
        matched = [prefix for prefix in prefixes if prefix in file.as_posix()]
        if (not file.is_relative_to(execution_root / 'bazel-out')
                or len(matched) != 1 or '..' in file.parts or file.suffix != '.o'):
            raise ValueError('Compiler output outside probe inventory')
        key = file.as_posix().split(matched[0], 1)[1]
        if key in result:
            raise ValueError('Ambiguous compiler output name')
        result[key] = file
    return result


def probe_objects(rows, execution_root, owner, package, variant, project_header=False, hybrid=False):
    """Match the selected producer's flat or grouped compiler output layout."""
    return owned_objects(rows, execution_root, owner,
                         split=project_header and variant != 'baseline', package=package,
                         groups=('document', 'string', 'plain') if hybrid and variant != 'baseline' else ())


def normalized_commands(rows, pch_path=None, eligible_sources=None, expected_count=None):
    """Preserve source, flags, include order and environment across variants."""
    result = {}
    for original, environment in rows:
        arguments = list(original)
        if '-c' not in arguments or '-o' not in arguments:
            raise ValueError('Expanded C++ compile command required')
        source = arguments[arguments.index('-c') + 1]
        selected_pch = pch_path.get(source) if isinstance(pch_path, dict) else pch_path
        uses_pch = selected_pch is not None and (eligible_sources is None or source in eligible_sources)
        if not uses_pch:
            if '-include-pch' in arguments:
                raise ValueError('Unexpected PCH on source: ' + source)
        else:
            if arguments.count('-fpch-validate-input-files-content') != 1:
                raise ValueError('Expected PCH content validation')
            arguments.remove('-fpch-validate-input-files-content')
            if arguments.count('-include-pch') != 1:
                raise ValueError('Expected one explicit PCH input')
            index = arguments.index('-include-pch')
            if arguments[index + 1] != selected_pch:
                raise ValueError('Compiler uses a different PCH')
            del arguments[index:index + 2]
            if eligible_sources is not None:
                if arguments.count('-ffile-prefix-map=./=') != 1:
                    raise ValueError('Expected exact PCH filename mapping')
                arguments.remove('-ffile-prefix-map=./=')
        if eligible_sources is not None and '-isysroot' in arguments:
            index = arguments.index('-isysroot')
            if arguments[index + 1] != '.':
                raise ValueError('Unexpected PCH relocation root')
            del arguments[index:index + 2]
        for option in ['-o', '-MF', '-MT']:
            if option in arguments:
                arguments[arguments.index(option) + 1] = '<output>'
        arguments = ['-frandom-seed=<output>' if value.startswith('-frandom-seed=') else value
                     for value in arguments]
        if source in result:
            raise ValueError('Duplicate source command')
        result[source] = arguments, environment
    count = len(SOURCES) if expected_count is None else expected_count
    if len(result) != count:
        raise ValueError('Incomplete compiler command inventory')
    return result


def verify_include_reduction(baseline, candidate):
    """Only remove Chromium-owned search paths; keep flags and search order."""
    def separate(arguments):
        flags, includes = [], []
        iterator = iter(arguments)
        for argument in iterator:
            if argument in ('-I', '-iquote', '-isystem', '-iframework'):
                includes.append((argument, next(iterator)))
            elif argument.startswith('-I'):
                includes.append(('-I', argument[2:]))
            else:
                flags.append(argument)
        return flags, includes

    def owned(path):
        path = posixpath.normpath(path)
        if path.startswith('bazel-out/'):
            parts = path.split('/', 3)
            if len(parts) == 4 and parts[2] == 'bin':
                path = parts[3]
        root = 'external/+chromium_dependencies+chromium'
        return path == root or path.startswith(root + '/')

    if baseline.keys() != candidate.keys():
        raise ValueError('Include candidate changes source inventory')
    counts = set()
    for source, (before, before_environment) in baseline.items():
        after, after_environment = candidate[source]
        before_flags, before_paths = separate(before)
        after_flags, after_paths = separate(after)
        if before_flags != after_flags or before_environment != after_environment:
            raise ValueError('Include candidate changes compiler flags or environment')
        remaining = iter(before_paths)
        removed = []
        for wanted in after_paths:
            for entry in remaining:
                if entry == wanted:
                    break
                removed.append(entry)
            else:
                raise ValueError('Include candidate adds or reorders search paths')
        removed.extend(remaining)
        if not removed or any(not owned(path) for _, path in removed):
            raise ValueError('Include candidate must only remove Chromium search paths')
        counts.add((len(before_paths), len(after_paths)))
    if len(counts) != 1:
        raise ValueError('Expected one include context for the fixed cohort')
    before, after = counts.pop()
    return {'baseline_paths': before, 'candidate_paths': after,
            'removed_paths': before - after, 'retained_order_verified': True,
            'other_flags_and_environments_equal': True}


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
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--hybrid', action='store_true')
    mode.add_argument('--include-context', action='store_true')
    mode.add_argument('--project-header', action='store_true',
                        help='Use the captured header only on original consumers')
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--sandbox-base', type=Path, required=True)
    parser.add_argument('--compiler-archive', type=Path, required=True)
    args = parser.parse_args()
    project = args.project_header or args.hybrid
    candidate_owner = ('blink_hybrid_pch_compile_probe' if args.hybrid else
                       'blink_include_context_probe' if args.include_context else
                       'blink_project_pch_compile_probe' if args.project_header else OWNER)
    candidate_variant = 'candidate' if args.include_context or args.hybrid else 'pch'
    package = 'tools/ci/compile/include_context' if args.include_context else PACKAGE
    targets = ({'baseline': '//' + package + ':baseline-linux-amd64',
                candidate_variant: '//' + package + ':linux-amd64'}
               if args.include_context else dict(TARGETS))
    if args.hybrid:
        targets = {'baseline': '//' + PACKAGE + ':hybrid-baseline-linux-amd64',
                   'candidate': '//' + PACKAGE + ':hybrid-linux-amd64'}
    eligible = None
    if project:
        assignments = ast.parse((ROOT / 'tools/ci/compile/project_pch_headers.bzl').read_text()).body
        metadata = {node.targets[0].id: ast.literal_eval(node.value) for node in assignments
                    if isinstance(node, ast.Assign)}
        eligible = {'external/+chromium_dependencies+chromium/' + value
                    for value in metadata['ELIGIBLE_SOURCES']}
        if not eligible or not set(metadata['ELIGIBLE_SOURCES']).issubset(SOURCES):
            raise ValueError('Project PCH consumers outside fixed cohort')
        if not args.hybrid:
            targets['pch'] = '//' + PACKAGE + ':project-linux-amd64'
        else:
            assignments = ast.parse((ROOT / 'tools/ci/compile/document_pch_headers.bzl').read_text()).body
            document = {node.targets[0].id: ast.literal_eval(node.value) for node in assignments
                        if isinstance(node, ast.Assign)}
            document_sources = {'external/+chromium_dependencies+chromium/' + value
                                for value in document['DOCUMENT_SOURCES']}
            if not document_sources or not document_sources.issubset(eligible):
                raise ValueError('Document consumers outside the validated string cohort')
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
              'complete': False, 'phases': {}, 'original_archive_sha256': ARCHIVE_SHA256}
    if args.include_context:
        report['measurement'] = 'Warm support; all selected compiles rebuilt; GN include context; not cold proof'
        report['sandbox_directory_reuse'] = False
    if project:
        if args.hybrid:
            report['project_headers'] = [document['DOCUMENT_HEADER'], metadata['HEADER']]
            report['source_groups'] = {'document': len(document_sources),
                                       'string': len(eligible - document_sources),
                                       'plain': len(SOURCES) - len(eligible)}
        else:
            report['project_header'] = metadata['HEADER']
        report['pch_consumer_count'] = len(eligible)
        report['sandbox_directory_reuse'] = False
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
                BAZEL_URL,
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
        if project or args.include_context:
            flags.append('--noreuse_sandbox_directories')
        try:
            execution_root = Path(subprocess.check_output(
                [*startup, 'info', 'execution_root'], cwd=source, text=True).strip())
            files = {}
            commands = {}
            pch = pch_relative = None
            pch_files = []
            if not args.include_context and not args.hybrid:
                pch_target = '//' + PACKAGE + ':' + candidate_owner + '_pch'
                pch_rows = query(startup, flags, source, '[f.path for f in target.files.to_list()]', pch_target)
                pch_relative, = pch_rows[0]
                pch = execution_root / pch_relative
                if ('..' in pch.parts or not pch.is_relative_to(execution_root / 'bazel-out')
                        or '/' + PACKAGE + '/' not in pch.as_posix() or pch.suffix != '.pch'):
                    raise ValueError('PCH output outside probe inventory')
                pch_files.append(pch)
            producer_targets = [] if args.include_context or args.hybrid else [pch_target]
            raw_pch = None
            if args.project_header:
                raw_rows = query(startup, flags, source,
                                 '[f.path for a in target.actions if a.mnemonic == "ChromiumProjectPch" for f in a.outputs.to_list() if f.path.endswith(".raw.pch")]', pch_target)
                raw_relative, = raw_rows[0]
                raw_pch = execution_root / raw_relative
                if (not raw_pch.is_relative_to(execution_root / 'bazel-out')
                        or '..' in raw_pch.parts
                        or '/' + PACKAGE + '/' not in raw_pch.as_posix()
                        or raw_pch.name != candidate_owner + '_pch.raw.pch'):
                    raise ValueError('Raw PCH outside probe inventory')
                pch_files.append(raw_pch)
            if args.hybrid:
                group_paths = {}
                for group in ('document', 'string'):
                    producer = candidate_owner + '_' + group + '_pch'
                    target = '//' + PACKAGE + ':' + producer
                    producer_targets.append(target)
                    verified, = query(startup, flags, source,
                                      '[f.path for f in target.files.to_list()]', target)[0]
                    raw, = query(startup, flags, source,
                                 '[f.path for a in target.actions if a.mnemonic == "ChromiumProjectPch" for f in a.outputs.to_list() if f.path.endswith(".raw.pch")]', target)[0]
                    for path, suffix in ((verified, '.pch'), (raw, '.raw.pch')):
                        output = execution_root / path
                        if (not output.is_relative_to(execution_root / 'bazel-out')
                                or '..' in output.parts or '/' + PACKAGE + '/' not in path
                                or output.name != producer + suffix):
                            raise ValueError('Hybrid PCH output outside probe inventory')
                        pch_files.append(output)
                    group_paths[group] = verified
                pch_relative = {source: group_paths['document' if source in document_sources else 'string']
                                for source in eligible}
            for producer in producer_targets:
                rows, = query(startup, flags, source,
                              '[a.argv for a in target.actions if a.mnemonic in ["ChromiumPch", "ChromiumProjectPch"]]', producer)
                if len(rows) != 1:
                    raise ValueError('Expected one PCH producer action')
                verify_producer_options(rows[0])
            for variant in targets:
                owner = ((candidate_owner if args.include_context or args.hybrid else OWNER) + '_baseline'
                         if variant == 'baseline' else candidate_owner)
                target = '//' + package + ':' + owner
                rows = query(startup, flags, source,
                             '[f.path for a in target.actions if a.mnemonic == "CppCompile" for f in a.outputs.to_list() if f.path.endswith(".o")]', target)
                files[variant] = probe_objects(
                    rows, execution_root, owner, package, variant,
                    project_header=args.project_header, hybrid=args.hybrid)
                rows, = query(startup, flags, source,
                              '[(a.argv, a.env) for a in target.actions if a.mnemonic == "CppCompile"]', target)
                commands[variant] = normalized_commands(
                    rows, pch_relative if variant == candidate_variant else None, eligible_sources=eligible)
            if args.include_context:
                report['include_reduction'] = verify_include_reduction(
                    commands['baseline'], commands[candidate_variant])
            else:
                if commands['baseline'] != commands[candidate_variant]:
                    raise ValueError('PCH consumer changes other compiler flags or environment')
                report['consumer_commands_equivalent'] = True
            report['compiler_context_sha256'] = hashlib.sha256(json.dumps(commands['baseline'], sort_keys=True).encode()).hexdigest()
            report['actual_binary_sha256'] = verify_compiler(root / 'output-base')
            verify_command_compilers(commands['baseline'], root / 'output-base', report['actual_binary_sha256'])
            if not args.include_context:
                compiler = next(iter(commands['baseline'].values()))[0][0]
                report['pch_reproducibility'] = verify_pch_reproducibility(
                    root / 'output-base' / compiler, root / 'pch-reproducibility',
                    report['actual_binary_sha256'])
            reference = None
            for name, variant in [('warmup-baseline', 'baseline'), ('warmup-' + candidate_variant, candidate_variant),
                                  ('baseline-1', 'baseline'), (candidate_variant + '-1', candidate_variant),
                                  (candidate_variant + '-2', candidate_variant), ('baseline-2', 'baseline')]:
                if not name.startswith('warmup'):
                    for file in files[variant].values():
                        file.unlink()
                    if variant == candidate_variant:
                        for output in pch_files:
                            output.unlink()
                print('Compile experiment: ' + name, flush=True)
                row, profile = measure(startup, flags, source, name, targets[variant], root)
                report['phases'][name] = row
                if not name.startswith('warmup'):
                    row['selected_compiles'] = local_compile_times(profile, SOURCES)
                    data = row['build_metrics'].get('actionSummary', {}).get('actionData', [])
                    counts = {item['mnemonic']: int(item.get('actionsExecuted', 0)) for item in data}
                    if counts.get('CppCompile') != len(SOURCES) or counts.get('ChromiumPython', 0):
                        raise ValueError('Measured pass recompiles supporting actions')
                    pch_mnemonic = 'ChromiumProjectPch' if project else 'ChromiumPch'
                    expected_pch = (2 if args.hybrid else 1) if variant == candidate_variant and not args.include_context else 0
                    if counts.get(pch_mnemonic, 0) != expected_pch:
                        raise ValueError('PCH must rebuild exactly once in each candidate pass')
                    if counts.get('ChromiumPchClosure', 0) != (expected_pch if project else 0):
                        raise ValueError('Project PCH closure must validate each fresh candidate')
                hashes = {key: hashlib.sha256(file.read_bytes()).hexdigest() for key, file in files[variant].items()}
                current = row['archive_sha256'], hashes
                if reference is None:
                    if row['archive_sha256'] != ARCHIVE_SHA256:
                        raise ValueError('Frozen original cohort archive changed')
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
