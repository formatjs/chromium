"""Compare local sandbox costs with real compiles and matching archive bytes."""

import argparse
from bisect import bisect_left, bisect_right
import gzip
import json
import os
from pathlib import Path
import re
import subprocess
import time
import uuid

from tools.ci.compile.experiment import archive_outputs, compiler_input_diff, compiler_pattern


ROOT = Path(__file__).resolve().parents[3]
TARGET = '//tools/ci/compile/local:local-inputs-linux-amd64'
OWNERS = (':ml', ':gin', ':proto')
SOURCES = tuple('tensorflow/lite/kernels/' + name + '.cc' for name in (
    'activations', 'add', 'conv', 'fully_connected', 'quantize', 'reduce', 'dequantize', 'transpose',
)) + tuple('gin/' + name + '.cc' for name in (
    'arguments', 'array_buffer', 'context_holder', 'converter',
)) + tuple('components/optimization_guide/proto/' + name + '.pb.cc' for name in (
    'autocomplete_scoring_model_metadata', 'autofill_field_classification_model_metadata',
    'client_side_phishing_model_metadata', 'common_types',
))


def verify_ram_sandbox(path, mountinfo=Path('/proc/self/mountinfo')):
    path = path.resolve(strict=True)
    for line in mountinfo.read_text().splitlines():
        fields = line.split()
        mount = re.sub(r'\\([0-7]{3})', lambda match: chr(int(match[1], 8)), fields[4])
        if mount != str(path):
            continue
        if fields[fields.index('-') + 1] != 'tmpfs':
            break
        if any(path.iterdir()):
            raise ValueError('RAM sandbox must start empty')
        return path
    raise ValueError('RAM sandbox must be a dedicated tmpfs mount')


def _profile_events(profile):
    """Stream large Bazel traces without retaining unrelated events."""
    with gzip.open(profile, 'rt') as stream:
        buffer = ''
        marker = None
        while marker is None:
            chunk = stream.read(65536)
            if not chunk:
                raise ValueError('Missing profile trace events')
            buffer += chunk
            marker = re.search(r'"traceEvents"\s*:\s*\[', buffer)
        prefix = buffer[:marker.start()]
        buffer = buffer[marker.end():]
        decoder = json.JSONDecoder()
        after_value = False
        allow_end = True
        while True:
            buffer = buffer.lstrip()
            if not buffer:
                buffer = stream.read(65536)
                if not buffer:
                    raise ValueError('Incomplete profile trace events')
                continue
            if buffer.startswith(']'):
                if not allow_end:
                    raise ValueError('Invalid profile event separator')
                json.loads(prefix + '"traceEvents":[]' + buffer[1:] + stream.read())
                return
            if after_value:
                if not buffer.startswith(','):
                    raise ValueError('Missing profile event separator')
                buffer = buffer[1:]
                after_value = False
                allow_end = False
                continue
            try:
                event, end = decoder.raw_decode(buffer)
            except json.JSONDecodeError:
                chunk = stream.read(65536)
                if not chunk:
                    raise ValueError('Incomplete profile trace events') from None
                buffer += chunk
                continue
            yield event
            buffer = buffer[end:]
            after_value = True
            allow_end = True


def local_compile_times(profile, sources):
    sources = tuple(dict.fromkeys(sources))
    spans = [event for event in _profile_events(profile)
             if event.get('ph') == 'X' and event.get('dur', 0) > 0
             and (event.get('cat') == 'action processing'
                  and event.get('args', {}).get('mnemonic') == 'CppCompile'
                  or event.get('name') in ('subprocess.run', 'sandbox.createFileSystem'))]
    requested = {}
    unqualified = []
    for source in sources:
        if '/' in source:
            requested.setdefault(source.rsplit('/', 1)[-1], []).append(source)
        else:
            unqualified.append(source)
    matches = {source: [] for source in sources}
    threads = {}
    for event in spans:
        threads.setdefault(event.get('tid'), []).append(event)
        if event.get('cat') != 'action processing' or event.get('args', {}).get('mnemonic') != 'CppCompile':
            continue
        name = event.get('name', '').removesuffix(' [for tool]')
        basename = name.rsplit('/', 1)[-1].removeprefix('Compiling ')
        for source in requested.get(basename, []) + unqualified:
            if name.endswith(source):
                matches[source].append(event)
    starts = {}
    for thread, events in threads.items():
        events.sort(key=lambda event: event['ts'])
        starts[thread] = [event['ts'] for event in events]
    results = {}
    for source in sources:
        if len(matches[source]) != 1:
            raise ValueError('Expected one completed compiler span: ' + source)
        action = matches[source][0]
        thread = action.get('tid')
        end = action['ts'] + action['dur'] + 1000
        first = bisect_left(starts[thread], action['ts'])
        last = bisect_right(starts[thread], end)
        nested = [event for event in threads[thread][first:last]
                  if event['ts'] + event['dur'] <= end]
        subprocess_seconds = sum(event['dur'] for event in nested if event.get('name') == 'subprocess.run') / 1e6
        if subprocess_seconds <= 0:
            raise ValueError('Expected actual local compiler execution: ' + source)
        results[source] = {
            'action_seconds': action['dur'] / 1e6,
            'subprocess_seconds': subprocess_seconds,
            'sandbox_creation_seconds': sum(event['dur'] for event in nested
                                            if event.get('name') == 'sandbox.createFileSystem') / 1e6,
        }
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--repository-cache', type=Path, required=True)
    parser.add_argument('--bazel', default=os.environ.get('BAZEL', 'bazel'))
    parser.add_argument('--bb', default='bb', help='CLI used only for offline execution-log comparisons')
    parser.add_argument('--jobs', type=int, default=16)
    parser.add_argument('--comparison', choices=['include-scan', 'inmemory-sandboxes', 'ram-sandboxes'], default='include-scan')
    parser.add_argument('--sandbox-base', type=Path, help='Empty private tmpfs mount for RAM sandbox comparison')
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error('--jobs must be positive')
    if args.comparison == 'ram-sandboxes':
        if args.sandbox_base is None:
            parser.error('--comparison=ram-sandboxes requires --sandbox-base')
        args.sandbox_base = verify_ram_sandbox(args.sandbox_base)
    elif args.sandbox_base is not None:
        parser.error('--sandbox-base requires --comparison=ram-sandboxes')
    directory = args.directory.resolve()
    directory.mkdir(parents=True, exist_ok=False)
    output_base = directory / 'output-base'
    startup = [args.bazel, '--nosystem_rc', '--nohome_rc', '--noworkspace_rc',
               '--bazelrc=' + str(ROOT / '.bazelrc'), '--host_jvm_args=-Xmx12g',
               '--output_user_root=' + str(directory / 'bazel-root'),
               '--output_base=' + str(output_base), '--install_base=' + str(directory / 'install-base')]
    report = {'comparison': args.comparison, 'source_count': len(SOURCES),
              'measurement': 'warm supporting setup; selected compiles forced in every pass; not cold-build proof',
              'internal_timing_scope': 'recorded task spans; short operations may be coalesced',
              'jobs': args.jobs, 'modes': {}}
    if args.sandbox_base:
        report['sandbox_filesystem'] = {'type': 'tmpfs', 'initially_empty': True,
                                        'path': str(args.sandbox_base), 'build_uid': os.geteuid(),
                                        'capacity_bytes': os.statvfs(args.sandbox_base).f_blocks * os.statvfs(args.sandbox_base).f_frsize}
    nonce = uuid.uuid4().hex
    variant = args.comparison
    modes = [('warmup-baseline', False), ('warmup-' + variant, True),
             ('baseline-1', False), (variant + '-1', True),
             (variant + '-2', True), ('baseline-2', False)]
    def save():
        (directory / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    environment = os.environ.copy()
    environment.update({'CCACHE_DISABLE': '1', 'SCCACHE_DISABLE': '1'})
    try:
        for mode, experimental in modes:
            events = directory / (mode + '.events.json')
            profile = directory / (mode + '.profile.gz')
            command = [*startup, 'build', '--config=browser',
                       '--spawn_strategy=sandboxed', '--jobs=' + str(args.jobs),
                       '--local_resources=cpu=' + str(args.jobs), '--local_resources=memory=24000',
                       '--remote_executor=', '--remote_cache=', '--disk_cache=', '--repo_contents_cache=',
                       '--remote_accept_cached=false', '--noremote_upload_local_results',
                       '--bes_backend=', '--bes_results_url=',
                       '--repository_cache=' + str(args.repository_cache.resolve()),
                       '--extra_execution_platforms=//platforms:buildbuddy_linux_amd64',
                       '--build_event_json_file=' + str(events), '--nobuild_event_json_file_path_conversion',
                       '--profile=' + str(profile), '--record_full_profiler_data',
                       '--execution_log_compact_file=' + str(directory / (mode + '.binpb.zst')),
                       '--experimental_profile_include_target_label',
                       '--modify_execution_info=CppCompile=+no-cache',
                       '--per_file_copt=' + compiler_pattern(SOURCES) + '@-DBAZEL_COMPILE_PROFILE_RUN=' + nonce + '_' + mode.replace('-', '_'),
                       '--cc_include_scanning=true',
                       '--define=CHROMIUM_COMPILE_PROBE_SCAN=' + ('1' if variant == 'include-scan' and experimental else '0'),
                       '--experimental_inmemory_sandbox_stashes=' + ('true' if variant == 'inmemory-sandboxes' and experimental else 'false'),
                       '--sandbox_base=' + (str(args.sandbox_base) if variant == 'ram-sandboxes' and experimental else ''),
                       TARGET]
            started = time.monotonic()
            print(mode + ' START', flush=True)
            with (directory / (mode + '.log')).open('w') as log:
                result = subprocess.run(command, cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT)
            row = {'exit_code': result.returncode, 'wall_seconds': time.monotonic() - started}
            report['modes'][mode] = row
            save()
            if result.returncode:
                raise RuntimeError(mode + ' failed; see its build log')
            hashes, metrics = archive_outputs(events, TARGET)
            runners = metrics.get('actionSummary', {}).get('runnerCount', [])
            if not any(r.get('name') == 'linux-sandbox' and int(r.get('count', 0)) > 0 for r in runners):
                raise ValueError('No Linux sandbox execution recorded')
            if any('remote' in r.get('name', '').lower() and int(r.get('count', 0)) > 0 for r in runners):
                raise ValueError('Unexpected remote execution/cache reuse')
            row.update({'compiles': local_compile_times(profile, SOURCES),
                        'output_sha256': hashes, 'build_metrics': metrics})
            save()
            print(mode + ' DONE ' + str(round(row['wall_seconds'], 2)) + 's', flush=True)
        reference = report['modes']['baseline-1']['output_sha256']
        report['output_bytes_match'] = all(row['output_sha256'] == reference for row in report['modes'].values())
        save()
        if not report['output_bytes_match']:
            raise ValueError('Compiler archive bytes changed')
        report['input_diff'] = {}
        for pair in ('1', '2'):
            path = directory / ('diff-' + pair + '.json')
            with path.open('w') as output:
                subprocess.run([args.bb, 'explain', '--old', str(directory / ('baseline-' + pair + '.binpb.zst')),
                                '--new', str(directory / (variant + '-' + pair + '.binpb.zst')),
                                '--output_format', 'json'], stdout=output, cwd=ROOT, check=True)
            difference = compiler_input_diff(path, OWNERS, expected_compiles=len(SOURCES))
            report['input_diff'][pair] = difference
            save()
            if difference['comparison'] != 'paired':
                raise ValueError('Compiler inputs could not be paired')
            if variant == 'include-scan' and difference['input_paths_removed'] <= difference['input_paths_added']:
                raise ValueError('Scanner did not reduce compiler input paths')
            if variant in {'inmemory-sandboxes', 'ram-sandboxes'} and (difference['input_paths_removed'] or difference['input_paths_added']):
                raise ValueError('Sandbox bookkeeping changed compiler inputs')
    finally:
        subprocess.run([*startup, 'shutdown'], cwd=ROOT, env=environment, stdout=subprocess.DEVNULL, check=True)
    print('PASS: real local compiles, matching archives, complete input comparisons', flush=True)


if __name__ == '__main__':
    main()
