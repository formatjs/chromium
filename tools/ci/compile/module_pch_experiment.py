"""Compare complete native PCH components with fixed resources and byte gates."""

import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request

from tools.ci.chromium import ROOT
from tools.ci.compile import pch_experiment as pch
from tools.ci.compile.local import local_compile_times, verify_ram_sandbox
from tools.ci.compile.pch_reproducibility import verify, verify_producer_options
from tools.ci.compiler_archive import configure_compiler, verify_compiler
from tools.ci.local_cold import BAZEL_SHA256, BAZEL_URL, machine_limits

OWNER = 'blink_modules_d49fc862a2e90d4a'
PACKAGE = 'external/+chromium_dependencies+chromium/native'
PREFIX = '@@+chromium_dependencies+chromium//native:'
ARCHIVE_SHA256 = '7ffc0134e1516101ea11dd1a6dacd7dc4fa3c415861694ecb82727232cdcdab7'
COUNT = 1711


COMPONENTS = {
    'module-bindings': {
        'owner': OWNER, 'count': COUNT, 'archive_sha256': ARCHIVE_SHA256,
        'group': 'idl', 'pch_consumers': COUNT - 2,
        'source_prefix': 'external/+chromium_dependencies+chromium/',
    },
    'v8-generated': {
        'owner': 'browser_v8_0583b2bb19f5557f', 'count': 248,
        'archive_sha256': '92861f441c27d045b914fdd4276a33fdabfebbdc10d382bc0d3907141c8fb022',
        'group': 'generated', 'pch_consumers': 246,
        'source_prefix': 'native/', 'prefix_guard': True,
    },
    'v8-base': {
        'owner': 'browser_v8_25a5dd0bb5046cea', 'count': 578,
        'archive_sha256': '9041d6d1d33071387ec0ac40c8cd81c1e27883bc726ee2a67e500f4345fb6607',
        'group': 'isolate', 'pch_consumers': 474,
        'source_prefix': 'external/+chromium_dependencies+chromium_v8/',
    },
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--component', choices=tuple(COMPONENTS), default='module-bindings')
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--sandbox-base', type=Path, required=True)
    parser.add_argument('--compiler-archive', type=Path, required=True)
    args = parser.parse_args()
    component = COMPONENTS[args.component]
    owner, count = component['owner'], component['count']
    archive_sha256, group = component['archive_sha256'], component['group']
    pch_consumers = component['pch_consumers']
    verify_ram_sandbox(args.sandbox_base)
    args.directory.mkdir(parents=True, exist_ok=False)
    machine = machine_limits()
    capacity = math.floor(machine['cpu_limit'])
    if capacity < 1:
        raise ValueError('Runner needs a positive CPU budget')
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    report = {'measurement': 'Warm supporting outputs; all selected compiles and candidate PCH rebuilt; not cold proof',
              'revision': revision, 'machine': machine, 'jobs': capacity, 'cpu_budget': capacity,
              'component': args.component, 'owner': owner,
              'source_count': count, 'pch_consumer_count': pch_consumers,
              'sandbox_directory_reuse': False, 'selected_output_group': 'archive',
              'complete': False, 'phases': {},
              'original_archive_sha256': archive_sha256}
    cache = Path.home() / '.cache/chromium-strict-cold-downloads'
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='chromium-module-pch-') as temporary:
        root = Path(temporary)
        source = root / 'source'
        source.mkdir()
        with subprocess.Popen(['git', 'archive', '--format=tar', revision], cwd=ROOT,
                              stdout=subprocess.PIPE) as checkout:
            with tarfile.open(fileobj=checkout.stdout, mode='r|') as archive:
                archive.extractall(source, filter='data')
            if checkout.wait():
                raise ValueError('Source checkout failed')
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
        flags = ['--config=browser', '--output_groups=archive', '--nodiscard_analysis_cache', '--track_incremental_state',
                 '--keep_state_after_build', '--spawn_strategy=linux-sandbox',
                 '--sandbox_base=' + str(args.sandbox_base), '--noreuse_sandbox_directories',
                 '--local_resources=memory=14000', '--jobs=' + str(capacity),
                 '--local_resources=cpu=' + str(capacity), '--remote_executor=', '--remote_cache=',
                 '--remote_accept_cached=false', '--noremote_upload_local_results', '--disk_cache=',
                 '--repo_contents_cache=', '--repository_cache=' + str(cache),
                 '--bes_backend=', '--bes_results_url=',
                 '--downloader_config=' + str(source / 'tools/ci/download_mirrors.cfg'),
                 '--extra_execution_platforms=//platforms:buildbuddy_linux_amd64',
                 '--define=CHROMIUM_NATIVE_TOOLS=1', '--define=CHROMIUM_BLINK_PCH=1',
                 '--extra_toolchains=@chromium//native/tool_configuration:native_linux_execution',
                 '--define=CHROMIUM_COMPILE_PROBE_SCAN=1', '--define=CHROMIUM_BINDINGS_WORKERS=4']
        targets = {'baseline': PREFIX + owner, 'candidate': PREFIX + owner + '_pch'}
        try:
            execution = Path(subprocess.check_output([*startup, 'info', 'execution_root'],
                                                     cwd=source, text=True).strip())
            inventories, objects = {}, {}
            for variant, target in targets.items():
                rows, = pch.query(startup, flags, source,
                                 '[(a.argv,a.env,[f.path for f in a.outputs.to_list() if f.path.endswith(".o")]) for a in target.actions if a.mnemonic == "CppCompile"]', target)
                inventories[variant] = rows
                objects[variant] = pch.owned_objects(
                    [outputs for arguments, environment, outputs in rows], execution,
                    owner if variant == 'baseline' else owner + '_pch', package=PACKAGE,
                    groups=(group, 'plain') if variant == 'candidate' else (), expected_count=count)
            original = [(arguments, environment) for arguments, environment, outputs in inventories['baseline']]
            candidate = [(arguments, environment) for arguments, environment, outputs in inventories['candidate']]
            mapping = {arguments[arguments.index('-c') + 1]: arguments[arguments.index('-include-pch') + 1]
                       for arguments, environment in candidate if '-include-pch' in arguments}
            if len(mapping) != pch_consumers:
                raise ValueError('Component PCH consumer inventory changed')
            before = pch.normalized_commands(original, expected_count=count)
            after = pch.normalized_commands(candidate, mapping, eligible_sources=set(mapping), expected_count=count)
            if before != after:
                raise ValueError('Component PCH changes compiler flags or environment')
            report['consumer_commands_equivalent'] = True
            report['compiler_context_sha256'] = hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest()
            report['actual_binary_sha256'] = verify_compiler(root / 'output-base')
            pch.verify_command_compilers(before, root / 'output-base', report['actual_binary_sha256'])
            compiler = next(iter(before.values()))[0][0]
            report['pch_reproducibility'] = verify(root / 'output-base' / compiler,
                                                  root / 'pch-reproducibility', report['actual_binary_sha256'])
            producer = PREFIX + owner + '_' + group + '_pch'
            producer_rows, = pch.query(startup, flags, source,
                                      '[(a.argv,[f.path for f in a.outputs.to_list()]) for a in target.actions if a.mnemonic in ["ChromiumProjectPch","ChromiumPchClosure"]]', producer)
            raw, = [arguments for arguments, outputs in producer_rows if '-x' in arguments]
            verify_producer_options(raw)
            pch_outputs = [execution / path for arguments, outputs in producer_rows for path in outputs]
            expected = {owner + '_' + group + '_pch' + suffix for suffix in ['.raw.pch', '.d', '.pch']}
            if (len(pch_outputs) != 3 or {path.name for path in pch_outputs} != expected
                    or any(not path.is_relative_to(execution / 'bazel-out') or '..' in path.parts
                           or '/' + PACKAGE + '/' not in path.as_posix() for path in pch_outputs)):
                raise ValueError('PCH outputs outside expected inventory')
            if component.get('prefix_guard'):
                guard_rows, = pch.query(startup, flags, source,
                                       '[f.path for a in target.actions if a.mnemonic == "ChromiumPchPrefix" for f in a.outputs.to_list()]',
                                       PREFIX + owner + '_prefix_guard')
                if len(guard_rows) != 1 or guard_rows[0] != 'bazel-out/k8-fastbuild/bin/' + PACKAGE + '/' + owner + '_prefix_guard.validated':
                    raise ValueError('Unexpected PCH prefix guard output')
                pch_outputs.append(execution / guard_rows[0])
            reference = None
            sources = tuple(path.removeprefix('bazel-out/k8-fastbuild/bin/').removeprefix(
                'external/+chromium_dependencies+chromium/').removeprefix(
                component['source_prefix']) for path in before)
            for name, variant in [('warmup-baseline', 'baseline'), ('warmup-candidate', 'candidate'),
                                  ('baseline-1', 'baseline'), ('candidate-1', 'candidate'),
                                  ('candidate-2', 'candidate'), ('baseline-2', 'baseline')]:
                if not name.startswith('warmup'):
                    for path in list(objects[variant].values()) + (pch_outputs if variant == 'candidate' else []):
                        if path.is_symlink() or not path.is_file():
                            raise ValueError('Inventoried output missing or replaced by symlink')
                        path.unlink()
                row, profile = pch.measure(startup, flags, source, name, targets[variant], root, output_group="archive")
                report['phases'][name] = row
                if not name.startswith('warmup'):
                    row['selected_compiles'] = local_compile_times(profile, sources)
                    counts = {item['mnemonic']: int(item.get('actionsExecuted', 0)) for item in
                              row['build_metrics'].get('actionSummary', {}).get('actionData', [])}
                    expected_pch = int(variant == 'candidate')
                    if (counts.get('CppCompile') != count or counts.get('ChromiumPython', 0)
                            or counts.get('ChromiumProjectPch', 0) != expected_pch
                            or counts.get('ChromiumPchClosure', 0) != expected_pch
                            or counts.get('ChromiumPchPrefix', 0) != expected_pch * int(component.get('prefix_guard', False))):
                        raise ValueError('Measured pass contains missing selected or extra supporting actions')
                hashes = {key: hashlib.sha256(path.read_bytes()).hexdigest() for key, path in objects[variant].items()}
                current = row['archive_sha256'], hashes
                if reference is None:
                    if row['archive_sha256'] != archive_sha256:
                        raise ValueError('Frozen original component archive changed')
                    reference = current
                if current != reference:
                    raise ValueError('Component PCH changes original objects or archive')
                row['object_and_archive_bytes_match'] = True
                print(json.dumps({'phase': name, 'wall_seconds': row['wall_seconds'], 'bytes_match': True}), flush=True)
            report['complete'] = True
        except Exception as error:
            report['error'] = str(error)
            raise
        finally:
            subprocess.run([*startup, 'shutdown'], cwd=source, check=False, stdout=subprocess.DEVNULL)
            (args.directory / 'report.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
