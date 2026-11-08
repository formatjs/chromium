"""Compare bounded Blink workers with complete generated-output hashes."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from urllib.parse import unquote, urlparse
import urllib.request

from tools.ci.chromium import ROOT
from tools.ci.compile.local import verify_ram_sandbox
from tools.ci.local_cold import BAZEL_SHA256, machine_limits


TARGET = '@chromium//native:blink_core_d891bf49f6c231ad_0'


def output_hashes(events):
    sets, roots = {}, []
    completed = False
    for line in events.read_text().splitlines():
        event = json.loads(line)
        if 'namedSetOfFiles' in event:
            sets[event['id']['namedSet']['id']] = event['namedSetOfFiles']
        labels = {TARGET, '@@+chromium_dependencies+chromium' + TARGET.removeprefix('@chromium')}
        if event.get('id', {}).get('targetCompleted', {}).get('label') in labels:
            completed = event['completed']['success']
            for group in event['completed'].get('outputGroup', []):
                if group['name'] == 'default':
                    roots.extend(item['id'] for item in group.get('fileSets', []))
    outputs, visited = {}, set()
    while roots:
        identifier = roots.pop()
        if identifier in visited:
            continue
        visited.add(identifier)
        group = sets[identifier]
        roots.extend(item['id'] for item in group.get('fileSets', []))
        for item in group.get('files', []):
            uri = urlparse(item['uri'])
            if uri.scheme != 'file' or uri.netloc:
                raise ValueError('Generator outputs must be local')
            path = Path(unquote(uri.path))
            logical = path.as_posix().split('/native/gen/', 1)[1]
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if logical in outputs:
                raise ValueError('Duplicate generated output')
            outputs[logical] = digest
    if not completed or len(outputs) != 5574:
        raise ValueError('Expected all 5574 declared Blink bindings outputs')
    return outputs


def generator_seconds(profile):
    with gzip.open(profile, 'rt') as source:
        events = json.load(source)['traceEvents']
    spans = [event for event in events if event.get('ph') == 'X'
             and event.get('cat') == 'action processing'
             and 'blink_core_d891bf49f6c231ad_0' in event.get('name', '')
             and event.get('dur', 0) > 0]
    if len(spans) != 1:
        raise ValueError('Expected one real Blink generator timing span')
    return spans[0]['dur'] / 1e6


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--repository-cache', type=Path, required=True)
    parser.add_argument('--bazel', type=Path)
    parser.add_argument('--sandbox-base', type=Path, required=True)
    args = parser.parse_args()
    verify_ram_sandbox(args.sandbox_base)
    args.directory.mkdir(parents=True, exist_ok=False)
    report = {'revision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(), 'worker_counts': [1, 4], 'measurement': 'Warm supporting setup; selected generator executes each pass; not cold-build proof',
              'machine': machine_limits(), 'modes': {}, 'all_bytes_identical': False}
    baseline = None
    with tempfile.TemporaryDirectory(prefix='chromium-generator-probe-') as temporary:
        root = Path(temporary)
        try:
            bazel = args.bazel.resolve(strict=True) if args.bazel else root / 'bazel-9.2.0'
            if not args.bazel:
                with urllib.request.urlopen(
                        'https://github.com/bazelbuild/bazel/releases/download/9.2.0/bazel-9.2.0-linux-x86_64',
                        timeout=120) as response, bazel.open('wb') as output:
                    shutil.copyfileobj(response, output)
            if hashlib.sha256(bazel.read_bytes()).hexdigest() != BAZEL_SHA256:
                raise ValueError('Bazel release checksum mismatch')
            bazel.chmod(0o755)
            for mode, selected in [('warmup-serial', False), ('warmup-four', True),
                                   ('serial-1', False), ('four-1', True),
                                   ('four-2', True), ('serial-2', False)]:
                print('Generator probe: ' + mode, flush=True)
                events, profile = root / 'events.json', root / 'profile.gz'
                command = [str(bazel), '--nosystem_rc', '--nohome_rc', '--noworkspace_rc',
                           '--bazelrc=' + str(ROOT / '.bazelrc'), '--batch', '--host_jvm_args=-Xmx8g',
                           '--output_user_root=' + str(root / 'bazel-root'),
                           '--output_base=' + str(root / 'output-base'), 'build', '--config=browser',
                           '--jobs=8', '--local_resources=cpu=8', '--local_resources=memory=10000',
                           '--spawn_strategy=linux-sandbox', '--sandbox_base=' + str(args.sandbox_base),
                           '--nouse_action_cache', '--remote_executor=', '--remote_cache=', '--disk_cache=',
                           '--repo_contents_cache=', '--remote_accept_cached=false',
                           '--repository_cache=' + str(args.repository_cache.resolve()),
                           '--noremote_upload_local_results', '--bes_backend=', '--bes_results_url=',
                           '--extra_execution_platforms=//platforms:buildbuddy_linux_amd64',
                           '--define=CHROMIUM_BINDINGS_WORKERS=' + ('4' if selected else '1'),
                           '--build_event_json_file=' + str(events), '--nobuild_event_json_file_path_conversion',
                           '--profile=' + str(profile), '--record_full_profiler_data', TARGET]
                started = time.monotonic()
                log = root / (mode + '.log')
                with log.open('w') as output:
                    with subprocess.Popen(command, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT) as process:
                        while True:
                            try:
                                process.wait(timeout=30)
                                break
                            except subprocess.TimeoutExpired:
                                print('Generator probe: ' + mode + ' running', flush=True)
                if process.returncode:
                    print(log.read_text(errors='replace')[-6000:], flush=True)
                    raise ValueError('Generator build failed: ' + mode)
                outputs = output_hashes(events)
                if baseline is None:
                    baseline = outputs
                if outputs != baseline:
                    raise ValueError('Generated bytes changed: ' + mode)
                report['modes'][mode] = {'generator_seconds': generator_seconds(profile),
                                         'total_seconds': time.monotonic() - started,
                                         'output_count': len(outputs)}
                print(json.dumps(report['modes'][mode]), flush=True)
            report['all_bytes_identical'] = True
        except Exception as error:
            report['error'] = str(error)
            raise
        finally:
            (args.directory / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
            print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
