"""Measure a complete local cold archive build, reusing dependency downloads only."""

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import subprocess
import tarfile
import time

from tools.ci.chromium import PLATFORMS, ROOT, artifact_outputs, cold_build_report
from tools.ci.compile.local import verify_ram_sandbox


BAZEL_SHA256 = '7668a95db1250f12c40407251e4e203b4ec8bf39bc495d2f485b2d8c99048694'
BAZEL_URL = 'https://releases.bazel.build/9.2.0/release/bazel-9.2.0-linux-x86_64'


def machine_limits():
    affinity_cpus = len(os.sched_getaffinity(0))
    cpus = float(affinity_cpus)
    memory = os.sysconf('SC_PHYS_PAGES') * os.sysconf('SC_PAGE_SIZE')
    cgroup_root = Path('/sys/fs/cgroup')
    for line in Path('/proc/self/cgroup').read_text().splitlines():
        if not line.startswith('0::'):
            continue
        path = cgroup_root / line.split('::', 1)[1].lstrip('/')
        while path.is_relative_to(cgroup_root):
            cpu_limit, memory_limit = path / 'cpu.max', path / 'memory.max'
            if cpu_limit.exists():
                quota, period = cpu_limit.read_text().split()
                if quota != 'max':
                    cpus = min(cpus, int(quota) / int(period))
            if memory_limit.exists():
                value = memory_limit.read_text().strip()
                if value != 'max':
                    memory = min(memory, int(value))
            if path == cgroup_root:
                break
            path = path.parent
    model = next((line.partition(':')[2].strip() for line in Path('/proc/cpuinfo').read_text().splitlines()
                  if line.startswith('model name')), platform.processor())
    return {'cpu_limit': cpus, 'affinity_cpu_count': affinity_cpus,
            'reported_processor_model': model, 'memory_limit_bytes': memory, 'system': platform.platform()}


NORMAL_PROJECT_PCH_NAMES = frozenset({
    'base_bind_complete_pch',
    'base_bind_default_pch',
    'blink_core_83e906bc2e906865_document_pch',
    'blink_core_83e906bc2e906865_string_pch',
    'blink_core_9d3a9043a4edc87b_idl_pch',
    'blink_modules_d49fc862a2e90d4a_idl_pch',
    'browser_9541da8b21719506_browser_pch',
    'browser_d48195c21c933c30_profile_pch',
    'browser_v8_0583b2bb19f5557f_generated_pch',
    'browser_v8_25a5dd0bb5046cea_isolate_pch',
    'content_b640bd1dddd3ce1d_frame_host_pch',
    'content_b640bd1dddd3ce1d_public_frame_host_pch',
})


def eager_template_pch_producers(source):
    manifest = source / 'overlays/chromium/bcr/overlay/native/eager_template_pch_data.bzl'
    if not manifest.exists():
        return frozenset()
    assignments = [node.value for node in ast.parse(manifest.read_text()).body
                   if isinstance(node, ast.Assign) and any(
                       isinstance(target, ast.Name) and target.id == 'EAGER_TEMPLATE_SOURCES'
                       for target in node.targets)]
    if len(assignments) != 1:
        raise ValueError('Expected one eager-template source manifest')
    producers = ast.literal_eval(assignments[0])
    if not isinstance(producers, dict):
        raise ValueError('Expected eager-template producer mapping')
    for name, owners in producers.items():
        if not isinstance(name, str) or not name or not isinstance(owners, dict) or not owners:
            raise ValueError('Invalid eager-template producer')
        for owner, paths in owners.items():
            if (not isinstance(owner, str) or not owner or not isinstance(paths, list) or not paths
                    or any(not isinstance(path, str) or not path for path in paths)):
                raise ValueError('Invalid eager-template source list')
    if not producers.keys() <= NORMAL_PROJECT_PCH_NAMES:
        raise ValueError('Unknown eager-template producer')
    return frozenset(producers)


def serialization_pch_producers(source):
    manifest = source / 'overlays/chromium/bcr/overlay/native/serialization_pch_data.bzl'
    if not manifest.exists():
        return frozenset()
    assignments = [node.value for node in ast.parse(manifest.read_text()).body
                   if isinstance(node, ast.Assign) and any(
                       isinstance(target, ast.Name) and target.id == 'SERIALIZATION_SOURCES'
                       for target in node.targets)]
    if len(assignments) != 1:
        raise ValueError('Expected one serialization source manifest')
    owners = ast.literal_eval(assignments[0])
    if not isinstance(owners, dict):
        raise ValueError('Expected serialization owner mapping')
    for owner, paths in owners.items():
        if (not isinstance(owner, str) or not owner or not isinstance(paths, list) or not paths
                or any(not isinstance(path, str) or not path for path in paths)):
            raise ValueError('Invalid serialization source list')
    return frozenset({'serialization_eager_pch'} if owners else ())


def v8_objects_pch_producers(source):
    manifest = source / 'overlays/chromium/bcr/overlay/native/v8_objects_pch_data.bzl'
    if not manifest.exists():
        return frozenset()
    values = {}
    for node in ast.parse(manifest.read_text()).body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in {'V8_OBJECTS_SOURCES', 'V8_OBJECTS_EAGER_SOURCES'}:
                if target.id in values:
                    raise ValueError('Duplicate V8 object source manifest')
                values[target.id] = ast.literal_eval(node.value)
    if values.keys() != {'V8_OBJECTS_SOURCES', 'V8_OBJECTS_EAGER_SOURCES'}:
        raise ValueError('Expected both V8 object source manifests')
    for owners in values.values():
        if not isinstance(owners, dict):
            raise ValueError('Expected V8 object owner mapping')
        for owner, paths in owners.items():
            if (not isinstance(owner, str) or not owner or not isinstance(paths, list) or not paths
                    or any(not isinstance(path, str) or not path for path in paths)):
                raise ValueError('Invalid V8 object source list')
    sources, eager = values['V8_OBJECTS_SOURCES'], values['V8_OBJECTS_EAGER_SOURCES']
    if any(not set(paths) <= set(sources.get(owner, [])) for owner, paths in eager.items()):
        raise ValueError('Eager V8 objects must belong to the expanded source set')
    required = {'v8_objects_eager_pch'} if eager else set()
    if any(set(paths) - set(eager.get(owner, [])) for owner, paths in sources.items()):
        required.add('v8_objects_normal_pch')
    return frozenset(required)


def pch_output_proof(directory, eager_producers, additional_producers=()):
    native = directory / ('output-base/execroot/_main/bazel-out/k8-fastbuild/bin/'
                          'external/+chromium_dependencies+chromium/native')
    required = {name + '_templates' for name in eager_producers} | set(additional_producers)
    allowed = NORMAL_PROJECT_PCH_NAMES | required
    raw = {path.name.removesuffix('.raw.pch'): path for path in native.glob('*.raw.pch')}
    validated = {path.name.removesuffix('.pch'): path for path in native.glob('*.pch')
                 if not path.name.endswith('.raw.pch')}
    verified = bool(required <= raw.keys() and raw.keys() == validated.keys() and raw.keys() <= allowed)
    if verified:
        for name, path in raw.items():
            other = validated[name]
            if path.is_symlink() or other.is_symlink() or not path.stat().st_size:
                verified = False
                break
            with path.open('rb') as first, other.open('rb') as second:
                if hashlib.file_digest(first, 'sha256').digest() != hashlib.file_digest(second, 'sha256').digest():
                    verified = False
                    break
    return {'verified': verified, 'produced': sorted(raw), 'validated': sorted(validated),
            'required_eager': sorted(name + '_templates' for name in eager_producers),
            'required_additional': sorted(additional_producers),
            'unused_original': sorted(NORMAL_PROJECT_PCH_NAMES - raw.keys())}


def set_timing_target(report, target_seconds):
    if target_seconds <= 0:
        raise ValueError('Timing target must be positive')
    report['target_seconds'] = target_seconds
    report['under_target'] = report['cold_result_verified'] and report['elapsed_seconds'] < target_seconds
    report['under_one_hour'] = report['cold_result_verified'] and report['elapsed_seconds'] < 3600


def local_cold_report(events, elapsed, success, directory, repository_cache, fresh, client_command=None,
                      expected_pch_count=0, expected_prefix_count=0, expected_base_bind_pch=False,
                      expected_eager_producers=(), expected_additional_producers=(), target_seconds=3600):
    if expected_base_bind_pch:
        expected_pch_count, expected_prefix_count = 12, 1
    report = cold_build_report(events, elapsed, success,
                               expected_output_base=directory / 'output-base',
                               output_base_was_fresh=fresh)
    options = {}
    if events.exists():
        with events.open() as stream:
            for line in stream:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                command = event.get('structuredCommandLine', {})
                if command.get('commandLineLabel') != 'canonical':
                    continue
                for section in command.get('sections', []):
                    for option in section.get('optionList', {}).get('option', []):
                        options.setdefault(option['optionName'], []).append(option.get('optionValue', ''))

    def matches(name, allowed):
        values = options.get(name, [])
        return len(values) == 1 and values[0] in allowed

    disabled = {'false', '0'}
    required = {
        'remote_executor': {''}, 'remote_cache': {''}, 'disk_cache': {''},
        'repo_contents_cache': {''}, 'remote_accept_cached': disabled,
        'remote_upload_local_results': disabled, 'use_action_cache': disabled,
        'batch': {'true', '1'}, 'spawn_strategy': {'linux-sandbox'},
        'install_base': {str(directory / 'install-base')},
        'output_user_root': {str(directory / 'bazel-root')},
        'repository_cache': {str(repository_cache)},
    }
    # RC switches are client-only and absent from canonical BEP startup flags.
    startup = client_command[1:client_command.index('build')] if client_command and 'build' in client_command else []
    rc_switches = [value for value in startup if re.match(r'^--(?:no)?(?:system_rc|home_rc|workspace_rc)(?:=|$)', value)]
    client_verified = (sorted(rc_switches) == sorted(['--nosystem_rc', '--nohome_rc', '--noworkspace_rc'])
                       and [value for value in startup if value.startswith('--bazelrc')]
                       == ['--bazelrc=' + str(directory / 'source/.bazelrc')]
                       and not any(value.startswith('--ignore_all_rc_files') for value in startup))
    optional_rc = all(name not in options or matches(name, disabled)
                      for name in ['system_rc', 'home_rc', 'workspace_rc'])
    policy = client_verified and optional_rc and all(matches(name, allowed) for name, allowed in required.items())
    runners = report.get('build_metrics', {}).get('actionSummary', {}).get('runnerCount', [])
    actual = {row.get('name') for row in runners if int(row.get('count', 0)) > 0}
    local = 'linux-sandbox' in actual and actual <= {'total', 'internal', 'linux-sandbox'}
    # Local BEP can omit empty cache statistics. Require canonical disabling,
    # fresh state and actual sandbox executions instead of assuming zero hits.
    report['local_policy_verified'] = policy
    report['client_configuration_verified'] = client_verified
    action_data = report.get('build_metrics', {}).get('actionSummary', {}).get('actionData', [])
    report['project_pch_actions'] = sum(int(row.get('actionsExecuted', 0)) for row in action_data
                                      if row['mnemonic'] == 'ChromiumProjectPch')
    report['pch_closure_actions'] = sum(int(row.get('actionsExecuted', 0)) for row in action_data
                                      if row['mnemonic'] == 'ChromiumPchClosure')
    report['pch_prefix_actions'] = sum(int(row.get('actionsExecuted', 0)) for row in action_data
                                     if row['mnemonic'] == 'ChromiumPchPrefix')
    report['expected_prefix_count'] = expected_prefix_count
    report['expected_pch_count'] = expected_pch_count
    report['expected_eager_template_pch_count'] = len(expected_eager_producers)
    report['expected_additional_pch_count'] = len(expected_additional_producers)
    if expected_eager_producers or expected_additional_producers:
        # Unused original variants may be pruned; eager outputs remain mandatory.
        proof = pch_output_proof(directory, expected_eager_producers, expected_additional_producers)
        report['pch_output_proof'] = proof
        expected_pch_count = len(proof['produced'])
        report['expected_pch_count'] = expected_pch_count
        report['max_expected_pch_count'] = (len(NORMAL_PROJECT_PCH_NAMES) + len(expected_eager_producers)
                                            + len(expected_additional_producers))
    else:
        proof = {'verified': True}
    defines = dict(value.split('=', 1) for value in options.get('define', []) if '=' in value)
    report['base_bind_pch_configuration_verified'] = (
        defines.get('CHROMIUM_BASE_BIND_PCH') == '1' if expected_base_bind_pch else None)
    report['requested_pch_actions_verified'] = ((not expected_pch_count or
        (report['project_pch_actions'] == expected_pch_count and
         report['pch_closure_actions'] == expected_pch_count))
        and report['pch_prefix_actions'] == expected_prefix_count
        and proof['verified']
        and (not (expected_eager_producers or expected_additional_producers) or expected_base_bind_pch)
        and (not expected_base_bind_pch or report['base_bind_pch_configuration_verified']))
    report['cold_result_verified'] = bool(success and report['output_base_verified'] and policy and local
                                         and report['cached_actions'] == 0 and report['cpp_compile_actions'] > 0
                                         and report['requested_pch_actions_verified'])
    report['local_execution_verified'] = report['cold_result_verified']
    report['cache_state'].update({
        'local_action_cache': False if policy else 'unverified',
        'remote_cas': 'disabled' if policy else 'unverified',
        'repository_download_cache': 'shared fetched archives; fresh extraction' if policy else 'unverified',
        'auxiliary_tool_caches': 'fresh per run' if policy else 'unverified',
        'os_page_cache': 'uncontrolled',
    })
    set_timing_target(report, target_seconds)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--repository-cache', type=Path, required=True)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--platform', choices=sorted(PLATFORMS), default='linux-amd64')
    parser.add_argument('--bazel', type=Path, required=True, help='Verified Bazel 9.2.0 Linux amd64 executable')
    parser.add_argument('--jobs', type=int, default=16)
    parser.add_argument('--heap-gib', type=int, default=12)
    parser.add_argument('--action-memory-mb', type=int, default=24000)
    parser.add_argument('--native-tools', action='store_true', help='Opt into matching native Linux tool configurations')
    parser.add_argument('--project-pch', action='store_true', help='Opt into validated V8, Content and module PCH candidates')
    parser.add_argument('--base-bind-pch', action='store_true', help='Opt into qualified shared Base Bind.h PCH cohorts')
    parser.add_argument('--blink-pch', action='store_true', help='Opt into validated native Blink PCH')
    parser.add_argument('--binding-workers', type=int, choices=[1, 2, 4], default=1)
    parser.add_argument('--compiler-profile', choices=['cxx', 'chromium'], default='cxx')
    parser.add_argument('--compiler-archive', type=Path, help='Explicit SHA-pinned experimental compiler dependency')
    parser.add_argument('--profile', type=Path, help='Optional private profile path outside disposable build state')
    parser.add_argument('--resource-log', type=Path, help='Streaming Linux resource counters')
    parser.add_argument('--sandbox-base', type=Path, help='Optional empty private tmpfs mount')
    parser.add_argument('--target-seconds', type=int, default=3600, help='Elapsed-time acceptance target')
    parser.add_argument('--max-seconds', type=int,
                        help='Cancel after this many seconds; defaults to target, 0 disables the limit')
    args = parser.parse_args()
    if args.max_seconds is None:
        args.max_seconds = args.target_seconds
    if args.base_bind_pch and not args.project_pch:
        parser.error('--base-bind-pch requires --project-pch')
    if args.compiler_profile != 'cxx' and not args.compiler_archive:
        parser.error('--compiler-profile requires --compiler-archive')
    if args.project_pch and not args.blink_pch:
        parser.error('--project-pch requires --blink-pch')
    if args.blink_pch and (not args.native_tools or args.platform != 'linux-amd64'):
        parser.error('--blink-pch requires --native-tools on linux-amd64')
    if args.resource_log and args.resource_log.exists():
        parser.error('--resource-log must start absent')
    if args.profile and args.profile.exists():
        parser.error('--profile must start absent')
    if args.compiler_archive and args.platform != 'linux-amd64':
        parser.error('--compiler-archive is currently validated for linux-amd64 only')
    if args.native_tools and args.platform != 'linux-amd64':
        parser.error('--native-tools currently requires linux-amd64')
    if platform.system() != 'Linux' or platform.machine() not in {'x86_64', 'amd64'}:
        parser.error('Local benchmark currently requires a Linux amd64 host')
    if not re.fullmatch(r'[0-9a-f]{40}', args.revision):
        parser.error('--revision must be a full source commit SHA')
    if min(args.jobs, args.heap_gib, args.action_memory_mb, args.target_seconds) < 1 or args.max_seconds < 0:
        parser.error('Resource limits and --target-seconds must be positive; --max-seconds must be nonnegative')
    directory, cache = args.directory.resolve(), args.repository_cache.resolve()
    if directory.is_relative_to(cache) or cache.is_relative_to(directory):
        parser.error('Fetch cache and benchmark directory must be separate')
    if args.sandbox_base:
        args.sandbox_base = verify_ram_sandbox(args.sandbox_base)
    started = time.monotonic()
    if args.sandbox_base and 'CHROMIUM_LOCAL_COLD_STARTED' in os.environ:
        started = float(os.environ['CHROMIUM_LOCAL_COLD_STARTED'])
        if not 0 < started <= time.monotonic():
            raise ValueError('Invalid private sandbox setup timestamp')
    directory.mkdir(parents=True, exist_ok=False)
    source = directory / 'source'
    events = directory / 'events.json'
    profile = args.profile.resolve() if args.profile else directory / 'profile.json.gz'
    resource_log = args.resource_log.resolve() if args.resource_log else directory / 'resources.jsonl'
    roots = [directory / name for name in ['source', 'output-base', 'install-base', 'bazel-root']]
    fresh = all(not path.exists() for path in roots)
    assert fresh
    from tools.ci.storage_probe import filesystem_snapshot
    from tools.ci.resource_probe import resource_snapshot
    storage_paths = {'output': directory}
    if args.sandbox_base:
        storage_paths['sandbox'] = args.sandbox_base
    resource_initial = resource_snapshot()
    storage_initial = filesystem_snapshot(storage_paths)
    storage_minimum = {name: row['available_bytes'] for name, row in storage_initial.items()}
    success, code, error, cancelled = False, None, None, False
    process = None
    command = None
    compiler_dependency = None
    expected_eager_producers = ()
    expected_additional_producers = ()
    try:
        bazel = args.bazel.resolve(strict=True)
        if hashlib.sha256(bazel.read_bytes()).hexdigest() != BAZEL_SHA256:
            raise ValueError('Bazel executable does not match the pinned 9.2.0 Linux amd64 release')
        source.mkdir()
        with subprocess.Popen(['git', '-C', str(ROOT), 'archive', '--format=tar', args.revision],
                              stdout=subprocess.PIPE) as checkout:
            with tarfile.open(fileobj=checkout.stdout, mode='r|') as archive:
                archive.extractall(source, filter='data')
            if checkout.wait():
                raise ValueError('Source checkout failed')
        if (source / '.bazelversion').read_text().strip() != '9.2.0':
            raise ValueError('Source commit does not select Bazel 9.2.0')
        if args.base_bind_pch:
            expected_eager_producers = eager_template_pch_producers(source)
            expected_additional_producers = serialization_pch_producers(source) | v8_objects_pch_producers(source)
        if args.compiler_archive:
            from tools.ci.compiler_archive import configure_compiler
            compiler_dependency = configure_compiler(source, args.compiler_archive, args.compiler_profile)
        environment = os.environ.copy()
        for name, child in {
            'XDG_CACHE_HOME': 'xdg-cache', 'PIP_CACHE_DIR': 'pip-cache', 'UV_CACHE_DIR': 'uv-cache',
            'CARGO_HOME': 'cargo-home', 'RUSTUP_HOME': 'rustup-home', 'GOCACHE': 'go-cache',
            'GOMODCACHE': 'go-mod-cache', 'TMPDIR': 'tmp',
        }.items():
            path = directory / child
            path.mkdir()
            environment[name] = str(path)
        environment.update({'CCACHE_DISABLE': '1', 'SCCACHE_DISABLE': '1'})
        label = '//tools/ci:' + args.platform + '_archive'
        command = [str(bazel), '--nosystem_rc', '--nohome_rc', '--noworkspace_rc',
                   '--bazelrc=' + str(source / '.bazelrc'), '--batch',
                   '--host_jvm_args=-Xmx' + str(args.heap_gib) + 'g',
                   '--output_user_root=' + str(directory / 'bazel-root'),
                   '--output_base=' + str(directory / 'output-base'),
                   '--install_base=' + str(directory / 'install-base'),
                   'build', '--config=browser', '--keep_going', '--jobs=' + str(args.jobs),
                   '--local_resources=cpu=' + str(args.jobs),
                   '--local_resources=memory=' + str(args.action_memory_mb),
                   '--spawn_strategy=linux-sandbox', '--nouse_action_cache',
                   '--curses=no', '--color=no', '--terminal_columns=10000',
                   '--remote_executor=', '--remote_cache=', '--remote_accept_cached=false',
                   '--noremote_upload_local_results', '--disk_cache=', '--repo_contents_cache=',
                   '--repository_cache=' + str(cache),
                   '--downloader_config=' + str(source / 'tools/ci/download_mirrors.cfg'),
                   '--bes_backend=', '--bes_results_url=',
                   '--modify_execution_info=.*=+no-cache',
                   '--extra_execution_platforms=//platforms:buildbuddy_linux_amd64',
                   '--//tools/ci:revision=' + args.revision,
                   '--build_event_json_file=' + str(events), '--nobuild_event_json_file_path_conversion',
                   '--profile=' + str(profile), '--record_full_profiler_data',
                   '--experimental_record_metrics_for_all_mnemonics',
                   '--execution_log_compact_file=' + str(directory / 'execution.log'),
                   '--experimental_profile_include_primary_output', '--experimental_profile_include_target_label']
        if args.sandbox_base:
            command.append('--sandbox_base=' + str(args.sandbox_base))
        if args.native_tools:
            command.extend(['--define=CHROMIUM_NATIVE_TOOLS=1',
                            '--extra_toolchains=@chromium//native/tool_configuration:native_linux_execution'])
        if args.blink_pch:
            command.append('--define=CHROMIUM_BLINK_PCH=1')
        if args.project_pch:
            command.append('--define=CHROMIUM_PROJECT_PCH=1')
        if args.base_bind_pch:
            command.append('--define=CHROMIUM_BASE_BIND_PCH=1')
        if args.binding_workers != 1:
            command.append('--define=CHROMIUM_BINDINGS_WORKERS=' + str(args.binding_workers))
        if args.platform.startswith('windows-'):
            command.extend(['--repo_env=BAZEL_MSVC_RUNTIME_VISUAL_STUDIO_EULA=1',
                            '--repo_env=BAZEL_WINDOWS_SDK_EULA=1'])
        command.append(label)
        (directory / 'command.json').write_text(json.dumps(command, indent=2) + '\n')
        with (directory / 'build.log').open('w') as log:
            process = subprocess.Popen(command, cwd=source, env=environment,
                                       stdout=log, stderr=subprocess.STDOUT)
            while process.poll() is None:
                elapsed = time.monotonic() - started
                storage = filesystem_snapshot(storage_paths)
                for name, row in storage.items():
                    storage_minimum[name] = min(storage_minimum[name], row['available_bytes'])
                resources = resource_snapshot(process.pid)
                with resource_log.open('a') as samples:
                    samples.write(json.dumps({'elapsed_seconds': elapsed, 'resources': resources}) + '\n')
                (directory / 'progress.json').write_text(json.dumps({'elapsed_seconds': elapsed,
                    'platform': args.platform, 'bazel_pid_in_namespace': process.pid,
                    'storage': storage, 'resources': resources, 'profile_bytes': profile.stat().st_size if profile.exists() else 0}) + '\n')
                if args.max_seconds and elapsed >= args.max_seconds:
                    cancelled = True
                    process.send_signal(signal.SIGINT)
                    break
                time.sleep(5)
            code = process.wait()
        if code == 0:
            if compiler_dependency is not None:
                from tools.ci.compiler_archive import verify_compiler
                compiler_dependency['actual_binary_sha256'] = verify_compiler(directory / 'output-base', args.compiler_profile)
            artifacts = directory / 'artifacts'
            artifacts.mkdir()
            for path in artifact_outputs(events, label):
                shutil.copyfile(path, artifacts / path.name)
            success = True
    except BaseException as exception:
        error = type(exception).__name__ + ': ' + str(exception)
        if process is not None and process.poll() is None:
            process.send_signal(signal.SIGINT)
            code = process.wait()
        raise
    finally:
        report = local_cold_report(events, time.monotonic() - started, success, directory, cache, fresh, command,
                                   expected_pch_count=10 if args.project_pch else 3 if args.blink_pch else 0,
                                   expected_prefix_count=1 if args.project_pch else 0,
                                   expected_base_bind_pch=args.base_bind_pch,
                                   expected_eager_producers=expected_eager_producers,
                                   expected_additional_producers=expected_additional_producers,
                                   target_seconds=args.target_seconds)
        report.update({'revision': args.revision, 'platform': args.platform, 'exit_code': code,
                       'cancelled_after_limit': cancelled, 'error': error,
                       'jobs': args.jobs, 'heap_gib': args.heap_gib,
                       'action_memory_mb': args.action_memory_mb,
                       'native_tool_sharing_requested': args.native_tools,
                       'binding_workers': args.binding_workers,
                       'blink_pch_requested': args.blink_pch, 'project_pch_requested': args.project_pch,
                       'base_bind_pch_requested': args.base_bind_pch,
                       'compiler_dependency': compiler_dependency,
                       'resource_initial': resource_initial, 'resource_final': resource_snapshot(),
                       'storage_initial': storage_initial, 'storage_final': filesystem_snapshot(storage_paths),
                       'minimum_sampled_available_bytes': storage_minimum,
                       'source_checkout': 'fresh git archive from local fetched objects',
                       'sandbox_base': str(args.sandbox_base) if args.sandbox_base else 'fresh output-base sandbox',
                       'sandbox_capacity_bytes': (shutil.disk_usage(args.sandbox_base).total
                                                  if args.sandbox_base else None),
                       'bazel_sha256': BAZEL_SHA256,
                       'build_uid': os.geteuid(), 'machine': machine_limits()})
        report['elapsed_seconds'] = time.monotonic() - started
        set_timing_target(report, args.target_seconds)
        (directory / 'cold-build.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps({key: report[key] for key in ['elapsed_seconds', 'cpp_compile_actions',
              'cold_result_verified', 'target_seconds', 'under_target', 'under_one_hour', 'exit_code']}), flush=True)
    return 0 if report['under_target'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
