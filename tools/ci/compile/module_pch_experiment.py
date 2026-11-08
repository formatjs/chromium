"""Compare all native module binding objects with fixed resources and byte gates."""

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
    report = {'measurement': 'Warm supporting outputs; all module compiles and candidate PCH rebuilt; not cold proof',
              'revision': revision, 'machine': machine, 'jobs': capacity, 'cpu_budget': capacity,
              'source_count': COUNT, 'pch_consumer_count': COUNT - 2,
              'sandbox_directory_reuse': False, 'sandbox_cleanup': 'synchronous',
              'complete': False, 'phases': {},
              'original_archive_sha256': ARCHIVE_SHA256}
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
        flags = ['--config=browser', '--nodiscard_analysis_cache', '--track_incremental_state',
                 '--keep_state_after_build', '--spawn_strategy=linux-sandbox',
                 '--sandbox_base=' + str(args.sandbox_base), '--noreuse_sandbox_directories',
                 '--experimental_sandbox_async_tree_delete_idle_threads=0',
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
        targets = {'baseline': PREFIX + OWNER, 'candidate': PREFIX + OWNER + '_pch'}
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
                    OWNER if variant == 'baseline' else OWNER + '_pch', package=PACKAGE,
                    groups=('idl', 'plain') if variant == 'candidate' else (), expected_count=COUNT)
            original = [(arguments, environment) for arguments, environment, outputs in inventories['baseline']]
            candidate = [(arguments, environment) for arguments, environment, outputs in inventories['candidate']]
            mapping = {arguments[arguments.index('-c') + 1]: arguments[arguments.index('-include-pch') + 1]
                       for arguments, environment in candidate if '-include-pch' in arguments}
            if len(mapping) != COUNT - 2:
                raise ValueError('Module PCH consumer inventory changed')
            before = pch.normalized_commands(original, expected_count=COUNT)
            after = pch.normalized_commands(candidate, mapping, eligible_sources=set(mapping), expected_count=COUNT)
            if before != after:
                raise ValueError('Module PCH changes compiler flags or environment')
            report['consumer_commands_equivalent'] = True
            report['compiler_context_sha256'] = hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest()
            report['actual_binary_sha256'] = verify_compiler(root / 'output-base')
            pch.verify_command_compilers(before, root / 'output-base', report['actual_binary_sha256'])
            compiler = next(iter(before.values()))[0][0]
            report['pch_reproducibility'] = verify(root / 'output-base' / compiler,
                                                  root / 'pch-reproducibility', report['actual_binary_sha256'])
            producer = PREFIX + OWNER + '_idl_pch'
            producer_rows, = pch.query(startup, flags, source,
                                      '[(a.argv,[f.path for f in a.outputs.to_list()]) for a in target.actions if a.mnemonic in ["ChromiumProjectPch","ChromiumPchClosure"]]', producer)
            raw, = [arguments for arguments, outputs in producer_rows if '-x' in arguments]
            verify_producer_options(raw)
            pch_outputs = [execution / path for arguments, outputs in producer_rows for path in outputs]
            expected = {OWNER + '_idl_pch' + suffix for suffix in ['.raw.pch', '.d', '.pch']}
            if (len(pch_outputs) != 3 or {path.name for path in pch_outputs} != expected
                    or any(not path.is_relative_to(execution / 'bazel-out') or '..' in path.parts
                           or '/' + PACKAGE + '/' not in path.as_posix() for path in pch_outputs)):
                raise ValueError('PCH outputs outside expected inventory')
            reference = None
            sources = tuple(path.removeprefix('bazel-out/k8-fastbuild/bin/').removeprefix(
                'external/+chromium_dependencies+chromium/') for path in before)
            for name, variant in [('warmup-baseline', 'baseline'), ('warmup-candidate', 'candidate'),
                                  ('baseline-1', 'baseline'), ('candidate-1', 'candidate'),
                                  ('candidate-2', 'candidate'), ('baseline-2', 'baseline')]:
                if not name.startswith('warmup'):
                    for path in list(objects[variant].values()) + (pch_outputs if variant == 'candidate' else []):
                        if path.is_symlink() or not path.is_file():
                            raise ValueError('Inventoried output missing or replaced by symlink')
                        path.unlink()
                report['active_phase'] = name
                (args.directory / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
                row, profile = pch.measure(startup, flags, source, name, targets[variant], args.directory)
                report['phases'][name] = row
                if not name.startswith('warmup'):
                    row['selected_compiles'] = local_compile_times(profile, sources)
                    counts = {item['mnemonic']: int(item.get('actionsExecuted', 0)) for item in
                              row['build_metrics'].get('actionSummary', {}).get('actionData', [])}
                    expected_pch = int(variant == 'candidate')
                    if (counts.get('CppCompile') != COUNT or counts.get('ChromiumPython', 0)
                            or counts.get('ChromiumProjectPch', 0) != expected_pch
                            or counts.get('ChromiumPchClosure', 0) != expected_pch):
                        raise ValueError('Measured pass contains missing selected or extra supporting actions')
                hashes = {key: hashlib.sha256(path.read_bytes()).hexdigest() for key, path in objects[variant].items()}
                current = row['archive_sha256'], hashes
                if reference is None:
                    if row['archive_sha256'] != ARCHIVE_SHA256:
                        raise ValueError('Frozen original module archive changed')
                    reference = current
                if current != reference:
                    raise ValueError('Module PCH changes original objects or archive')
                row['object_and_archive_bytes_match'] = True
                (args.directory / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
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
