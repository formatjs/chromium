"""Measure native tool configuration sharing without executing build actions."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import urllib.request

from tools.ci.chromium import ROOT
from tools.ci.local_cold import BAZEL_SHA256, machine_limits


BASE = '9c5225584f470ae27c05f596373aefa377619714'
FILES = ['overlays/chromium/bcr/overlay/native/' + name
         for name in ['tool_inputs.bzl', 'python_action.bzl', 'resource_copy.bzl']]


def summarize_graph(path):
    data = json.loads(path.read_text())
    targets = {str(item['id']): item['label'] for item in data['targets']}
    configurations = {str(item['id']): item for item in data['configuration']}
    fingerprints, owners, counts = Counter(), Counter(), Counter()
    for action in data['actions']:
        if action['mnemonic'] != 'CppCompile':
            raise ValueError('Unexpected action mnemonic')
        configuration = configurations[str(action['configurationId'])]
        owner = targets[str(action['targetId'])]
        fingerprints[(owner, configuration['checksum'], action['actionKey'])] += 1
        owners[owner] += 1
        counts[configuration['mnemonic']] += 1
    return fingerprints, {'cpp_actions': sum(fingerprints.values()),
                          'cpp_by_configuration': dict(counts), 'top_owners': owners.most_common(20)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args()
    args.directory.mkdir(parents=True, exist_ok=False)
    report = {'stage': 'setup', 'base_revision': BASE, 'machine': machine_limits(),
              'measurement': 'Analysis only; warm supporting state; no cold timing claim'}

    def save():
        (args.directory / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report), flush=True)

    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT).strip():
        raise ValueError('Graph probe requires a clean checkout')
    prototype = {name: (ROOT / name).read_bytes() for name in FILES}
    try:
        subprocess.run(['git', 'fetch', '--depth=1', 'origin', BASE], cwd=ROOT, check=True)
        original = {name: subprocess.check_output(['git', 'show', BASE + ':' + name], cwd=ROOT)
                    for name in FILES}
        with tempfile.TemporaryDirectory(prefix='chromium-native-graph-') as temporary:
            root = Path(temporary)
            bazel = root / 'bazel-9.2.0'
            with urllib.request.urlopen(
                    'https://github.com/bazelbuild/bazel/releases/download/9.2.0/bazel-9.2.0-linux-x86_64',
                    timeout=120) as response, bazel.open('wb') as output:
                shutil.copyfileobj(response, output)
            if hashlib.sha256(bazel.read_bytes()).hexdigest() != BAZEL_SHA256:
                raise ValueError('Bazel release checksum mismatch')
            bazel.chmod(0o755)

            def query(name, enabled, *, register=False, expect_failure=False):
                report['stage'] = name
                save()
                command = [str(bazel), '--nosystem_rc', '--nohome_rc', '--noworkspace_rc',
                           '--bazelrc=' + str(ROOT / '.bazelrc'), '--batch',
                           '--host_jvm_args=-Xmx12g', '--host_jvm_args=-XX:ActiveProcessorCount=8',
                           '--output_user_root=' + str(root / 'bazel-root'),
                           '--output_base=' + str(root / 'output-base'),
                           'aquery', '--config=browser', '--jobs=8', '--loading_phase_threads=4',
                           '--extra_execution_platforms=//platforms:buildbuddy_linux_amd64',
                           '--remote_executor=', '--remote_cache=', '--disk_cache=',
                           '--repo_contents_cache=', '--repository_cache=' + str(root / 'fetch-cache'),
                           '--bes_backend=', '--bes_results_url=',
                           '--//tools/ci:revision=' + BASE,
                           '--define=CHROMIUM_NATIVE_TOOLS=' + str(enabled),
                           '--output=jsonproto', '--include_artifacts=false', '--include_commandline=false']
                if register:
                    command.append('--extra_toolchains=@chromium//native/tool_configuration:native_linux_execution')
                command.append('mnemonic("CppCompile", deps(//tools/ci:linux-amd64_archive))')
                graph, log = root / (name + '.json'), root / (name + '.log')
                with graph.open('w') as output, log.open('w') as errors:
                    result = subprocess.run(command, cwd=ROOT, stdout=output, stderr=errors)
                if expect_failure:
                    if (result.returncode == 0 or 'Native tool sharing requires the Linux AMD64 GNU 2.31 execution toolchain'
                            not in log.read_text(errors='replace')):
                        raise ValueError('Native executor guard did not reject missing registration')
                    report['native_executor_guard_verified'] = True
                    return None
                if result.returncode:
                    print(log.read_text(errors='replace')[-8000:], flush=True)
                    raise ValueError('aquery failed: ' + name)
                fingerprints, summary = summarize_graph(graph)
                report[name] = summary
                save()
                return fingerprints

            for name, contents in original.items():
                (ROOT / name).write_bytes(contents)
            baseline = query('original', 0)
            for name, contents in prototype.items():
                (ROOT / name).write_bytes(contents)
            disabled = query('prototype-disabled', 0)
            report['default_action_graph_identical'] = baseline == disabled
            if baseline != disabled:
                raise ValueError('Disabled prototype changed compile action graph')
            query('prototype-no-registration', 1, expect_failure=True)
            query('prototype-enabled', 1, register=True)
            report['cpp_actions_removed'] = (report['original']['cpp_actions']
                                             - report['prototype-enabled']['cpp_actions'])
            if report['cpp_actions_removed'] <= 0:
                raise ValueError('Prototype did not reduce compile actions')
            report['stage'] = 'graph checks passed; compilation and artifact checks still required'
    except Exception as error:
        report.update(stage='failed', error=str(error))
        raise
    finally:
        for name, contents in prototype.items():
            (ROOT / name).write_bytes(contents)
        save()


if __name__ == '__main__':
    main()
