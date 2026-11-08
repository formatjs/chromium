"""Collect BuildBuddy action counts and sanitized timing summaries for one revision."""

import argparse
from bisect import bisect_right
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import heapq
import hashlib
import json
import math
import os
from pathlib import Path
import re
import statistics
import urllib.request

from tools.ci.buildbuddy_artifacts import API_URL, COLD_WORKFLOW_PREFIXES, api_request, invocation_id
from tools.ci.trace_events import TraceEvents


RPC_URL = 'https://formatjs.buildbuddy.io/rpc/BuildBuddyService/'
MAX_TRACE_SUMMARY_BYTES = 32 * 1024 * 1024
LOCAL_SPAWN_MNEMONICS = (
    'CppCompile', 'CppLink', 'CppArchive', 'ChromiumPython',
    'ChromiumProjectPch', 'ChromiumPchClosure', 'Rustc', 'RustBindgen',
    'ChromiumBindgenLayout', 'ChromiumRustcCfg', 'ChromiumToolRuntime',
    'Genrule', 'RunBinary', 'CcAutoconfCheck', 'CcAutoconfHdr', 'CcStage0Compile',
    'Bison', 'GlibMkenums', 'PerfettoBuildflags', 'AomRtcdGen',
    'LibvpxRtcdHeader', 'CopyToDirectory',
)



def rpc(method, body):
    request = urllib.request.Request(
        RPC_URL + method, data=json.dumps(body).encode(),
        headers={'Content-Type': 'application/json',
                 'x-buildbuddy-api-key': os.environ['BUILDBUDDY_API_KEY']})
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)


def summarize(invocation):
    result = {key: invocation.get(key) for key in (
        'invocationId', 'command', 'pattern', 'success', 'durationUsec',
        'invocationStatus', 'cacheStats', 'targetConfiguredCount')}
    result['metrics'] = []
    result['profiles'] = []
    for event in invocation.get('event', []):
        build_event = event.get('buildEvent', {})
        if 'buildMetrics' in build_event:
            result['metrics'].append(build_event['buildMetrics'])
        for log in build_event.get('buildToolLogs', {}).get('log', []):
            if 'profile' in log.get('name', '') and log.get('uri', '').startswith('bytestream://'):
                result['profiles'].append({'name': log['name'], 'uri': log['uri']})
    return result


def compiler_work(events):
    """Attribute completed task spans to compiler intervals on the same thread."""
    threads, groups = {}, {}
    for event in events:
        name = event.get('name', '')
        if event.get('cat') != 'action processing' or not name.startswith('Compiling '):
            continue
        source = name.removeprefix('Compiling ').removesuffix(' [for tool]')
        if '/gen/' in source:
            source = source.split('/gen/', 1)[1]
        source = source.removeprefix('gen/')
        group = next((group for prefix, group in (
            ('third_party/blink/', 'blink'), ('third_party/v8/', 'v8'),
            ('v8/', 'v8'), ('chrome/', 'chrome'), ('components/', 'components'),
            ('content/', 'content'),
        ) if source.startswith(prefix)), 'other')
        row = groups.setdefault(group, {
            'compile_spans': 0, 'tool_compile_spans': 0, 'action_task_seconds': 0,
            'merkle_task_seconds': 0, 'worker_task_seconds': 0, 'worker_spans': 0,
            'input_discovery_task_seconds': 0, 'include_scanning_task_seconds': 0,
        })
        row['compile_spans'] += 1
        row['tool_compile_spans'] += int(name.endswith(' [for tool]'))
        row['action_task_seconds'] += event['dur'] / 1e6
        threads.setdefault(event.get('tid'), []).append((event['ts'], event['ts'] + event['dur'], group))
    indices = {}
    for thread, intervals in threads.items():
        intervals.sort()
        indices[thread] = ([item[0] for item in intervals], intervals)
    for event in events:
        field = None
        if event.get('cat') == 'general information' and event.get('name') == 'MerkleTreeComputer.buildForSpawn':
            field = 'merkle_task_seconds'
        elif event.get('cat') == 'Remote execution process wall time':
            field = 'worker_task_seconds'
        elif event.get('cat') == 'discover inputs':
            field = 'input_discovery_task_seconds'
        elif event.get('cat') == 'include scanner':
            field = 'include_scanning_task_seconds'
        index = indices.get(event.get('tid'))
        if field is None or index is None:
            continue
        starts, intervals = index
        position = bisect_right(starts, event['ts']) - 1
        if position < 0:
            continue
        start, end, group = intervals[position]
        if event['ts'] >= start and event['ts'] + event['dur'] <= end + 1000:
            groups[group][field] += event['dur'] / 1e6
            if field == 'worker_task_seconds':
                groups[group]['worker_spans'] += 1
    return groups


def local_action_work(events):
    """Attribute local subprocess and sandbox spans without exporting paths."""
    groups, threads = {}, {}
    for event in events:
        mnemonic = event.get('args', {}).get('mnemonic')
        if (event.get('cat') != 'action processing'
                or mnemonic not in LOCAL_SPAWN_MNEMONICS):
            continue
        group = ('BlinkBindings' if mnemonic == 'ChromiumPython'
                 and '/gen/third_party/blink/renderer/bindings/' in event.get('out', '')
                 else mnemonic)
        row = groups.setdefault(group, {'action_spans': 0, 'action_task_seconds': 0,
                                       'max_action_seconds': 0, 'subprocess_task_seconds': 0,
                                       'sandbox_task_seconds': 0})
        start_seconds = event['ts'] / 1e6
        end_seconds = (event['ts'] + event['dur']) / 1e6
        row['first_action_start_seconds'] = min(row.get('first_action_start_seconds', start_seconds), start_seconds)
        row['last_action_end_seconds'] = max(row.get('last_action_end_seconds', end_seconds), end_seconds)
        seconds = event['dur'] / 1e6
        row['action_spans'] += 1
        row['action_task_seconds'] += seconds
        row['max_action_seconds'] = max(row['max_action_seconds'], seconds)
        threads.setdefault(event.get('tid'), []).append((event['ts'], event['ts'] + event['dur'], group))
    indices = {}
    for thread, intervals in threads.items():
        intervals.sort()
        indices[thread] = ([item[0] for item in intervals], intervals)
    for event in events:
        field = {'subprocess.run': 'subprocess_task_seconds',
                 'sandbox.createFileSystem': 'sandbox_task_seconds'}.get(event.get('name'))
        index = indices.get(event.get('tid'))
        if field is None or index is None:
            continue
        starts, intervals = index
        position = bisect_right(starts, event['ts']) - 1
        if position < 0:
            continue
        start, end, group = intervals[position]
        if event['ts'] >= start and event['ts'] + event['dur'] <= end + 1000:
            groups[group][field] += event['dur'] / 1e6
    return groups


def target_timings(events):
    """Group observed spans by hashed target/configuration; keep labels private."""
    groups = {}
    for event in events:
        arguments = event.get('args', {})
        mnemonic, target = arguments.get('mnemonic'), arguments.get('target')
        if event.get('cat') != 'action processing' or not mnemonic or not target:
            continue
        output = event.get('out', '')
        configuration = output.split('/')[1] if output.startswith('bazel-out/') else ''
        target_hash = hashlib.sha256(target.lstrip('@').encode()).hexdigest()
        configuration_hash = hashlib.sha256(configuration.encode()).hexdigest() if configuration else ''
        key = target_hash, configuration_hash, mnemonic
        start, end = event['ts'] / 1e6, (event['ts'] + event['dur']) / 1e6
        row = groups.setdefault(key, {'observed_spans': 0, 'observed_task_seconds': 0,
                                      'first_start_seconds': start, 'last_end_seconds': end})
        row['observed_spans'] += 1
        row['observed_task_seconds'] += event['dur'] / 1e6
        row['first_start_seconds'] = min(row['first_start_seconds'], start)
        row['last_end_seconds'] = max(row['last_end_seconds'], end)
    return [dict(target_sha256=target, configuration_sha256=configuration,
                 mnemonic=mnemonic, **row)
            for (target, configuration, mnemonic), row in sorted(groups.items())]


def pch_event_schema(events):
    """Detect PCH spans whose metadata format differs from native C++ spans."""
    matches = [event for event in events if event.get('name', '').startswith(
        ('ChromiumProjectPch', 'ChromiumPchClosure')) or event.get('out', '').endswith('.pch')]
    return {'matching_events': len(matches),
            'completed_duration_spans': sum(event.get('ph') == 'X' and event.get('dur', 0) > 0
                                            for event in matches),
            'categories': dict(Counter(event.get('cat', '') for event in matches)),
            'phase_types': dict(Counter(event.get('ph', '') for event in matches)),
            'mnemonic_present': sum(bool(event.get('args', {}).get('mnemonic')) for event in matches),
            'argument_keys': sorted({key for event in matches for key in event.get('args', {})})}


def trace_summary(path, allow_partial=False):
    reader = TraceEvents(path, allow_partial=allow_partial)
    durations, phases, longest = [], [], []
    fields = ('cat', 'ts', 'dur', 'tid')
    phase_names = {'Launch Blaze', 'Initialize command', 'Evaluate target patterns',
                   'Load, analyze dependencies and build artifacts', 'Complete build'}
    operations = {
        'merkle': ('general information', 'MerkleTreeComputer.buildForSpawn'),
        'upload_missing_inputs': ('Remote execution upload time', 'upload missing inputs'),
        'worker_execution': ('Remote execution process wall time', None),
        'worker_queue': ('Remote execution queuing time', None),
        'output_download': ('Remote execution file fetching', None),
        'input_discovery': ('discover inputs', None),
        'include_scanning': ('include scanner', None),
    }
    tasks = {name: {'count': 0, 'microseconds': 0} for name in operations}
    counter_specs = [
        ('bazel_cpu', 'CPU usage (Bazel)', 'cpu', 'cores'),
        ('bazel_memory', 'Memory usage (Bazel)', 'memory', 'MB'),
        ('active_actions', 'action count', 'action', 'actions'),
    ]
    samples = {label: [] for label, _, _, _ in counter_specs}
    pch_categories, pch_phases, pch_keys = Counter(), Counter(), set()
    pch_count = pch_durations = pch_mnemonics = count = 0
    for count, event in enumerate(reader, 1):
        category, name = event.get('cat'), event.get('name', '')
        arguments = event.get('args', {})
        if category == 'build phase marker':
            phases.append({**{key: event.get(key) for key in (*fields, 'ph')},
                           **({'name': name} if name in phase_names else {})})
        if name.startswith(('ChromiumProjectPch', 'ChromiumPchClosure')) or event.get('out', '').endswith('.pch'):
            pch_count += 1
            pch_durations += int(event.get('ph') == 'X' and event.get('dur', 0) > 0)
            pch_mnemonics += int(bool(arguments.get('mnemonic')))
            pch_categories[event.get('cat', '')] += 1
            pch_phases[event.get('ph', '')] += 1
            pch_keys.update(arguments)
        if event.get('ph') == 'C':
            for label, counter_name, argument, _ in counter_specs:
                value = arguments.get(argument)
                if name == counter_name and isinstance(value, (int, float)) and math.isfinite(value):
                    samples[label].append(value)
        if event.get('ph') != 'X' or event.get('dur', 0) <= 0:
            continue
        heapq.heappush(longest, (event['dur'], -count, {key: event.get(key) for key in fields}))
        if len(longest) > 40:
            heapq.heappop(longest)
        for operation, (task_category, task_name) in operations.items():
            if category == task_category and (task_name is None or name == task_name):
                tasks[operation]['count'] += 1
                tasks[operation]['microseconds'] += event['dur']
        if (category == 'action processing'
                or category in {'Remote execution process wall time', 'discover inputs', 'include scanner'}
                or name in {'MerkleTreeComputer.buildForSpawn', 'subprocess.run', 'sandbox.createFileSystem'}):
            compact = {key: event[key] for key in ('cat', 'name', 'ts', 'dur', 'tid', 'out') if key in event}
            compact['args'] = {key: arguments[key] for key in ('mnemonic', 'target') if key in arguments}
            durations.append(compact)
    counters = {}
    for label, _, _, unit in counter_specs:
        values = samples[label]
        if values:
            counters[label] = {'samples': len(values), 'sample_mean': statistics.fmean(values),
                               'sample_max': max(values), 'unit': unit}
    return {'trace_complete': reader.complete, 'event_count': count,
            'compiler_work': compiler_work(durations),
            'local_action_work': local_action_work(durations),
            'target_timings': target_timings(durations),
            'pch_event_schema': {'matching_events': pch_count, 'completed_duration_spans': pch_durations,
                                 'categories': dict(pch_categories), 'phase_types': dict(pch_phases),
                                 'mnemonic_present': pch_mnemonics, 'argument_keys': sorted(pch_keys)},
            'phases': phases,
            'longest_events': [event for _, _, event in sorted(longest, reverse=True)],
            'tasks': {name: {'count': row['count'], 'task_seconds': row['microseconds'] / 1e6}
                      for name, row in tasks.items()}, 'counters': counters}


def strict_cold_timing_verified(outer, report):
    """Require service checkout and setup to fit the same one-hour budget."""
    try:
        full_seconds = int(outer.get('durationUsec')) / 1e6
        build_seconds = float(report.get('elapsed_seconds'))
    except (TypeError, ValueError):
        return False
    return (outer.get('success') is True
            and outer.get('invocationStatus') == 'COMPLETE_INVOCATION_STATUS'
            and report.get('cold_result_verified') is True
            and report.get('local_execution_verified') is True
            and 0 < build_seconds <= full_seconds < 3600)


class _ProfileDownload:
    def __init__(self, source):
        self.source = source
        self.size = 0

    def read(self, size):
        if size < 0:
            raise ValueError('Profile download must use bounded reads')
        data = self.source.read(size)
        self.size += len(data)
        if self.size > 32 * 1024 * 1024 * 1024:
            raise ValueError('Profile exceeds 32 GiB')
        return data


def collect(identifier):
    outer = rpc('GetInvocation', {'lookup': {
        'invocationId': identifier, 'fetchChildInvocations': True}})['invocation'][0]
    result = summarize(outer)
    result['children'] = []
    pattern = outer.get('pattern', [])
    cold_prefix = next((prefix for prefix in COLD_WORKFLOW_PREFIXES
                        if len(pattern) == 1 and pattern[0].startswith(prefix)), None)
    report_key = None
    cold_profile = None
    report_path = 'compile-input-experiment/report.json'
    if pattern == ['Chromium compile input experiment'] or (
            len(pattern) == 1 and pattern[0].startswith(('Chromium compile inputs ', 'Chromium compile throughput '))):
        report_key = 'compile_experiment'
    elif len(pattern) == 1 and pattern[0].startswith('Chromium compression benchmark '):
        report_key = 'compression_experiment'
        report_path = 'compression-experiment/report.json'
    elif len(pattern) == 1 and pattern[0].startswith('Chromium bindings budget '):
        report_key = 'bindings_experiment'
        report_path = 'bindings-budget/report.json'
    elif pattern == ['Chromium Clang phase profile']:
        report_key = 'clang_experiment'
        report_path = 'clang-profile/report.json'
    elif pattern == ['Chromium V8 generated PCH comparison']:
        report_key = 'pch_experiment'
        report_path = 'v8-generated-pch/report.json'
    elif pattern == ['Chromium V8 PCH comparison']:
        report_key = 'pch_experiment'
        report_path = 'v8-pch/report.json'
    elif pattern == ['Chromium module PCH comparison']:
        report_key = 'pch_experiment'
        report_path = 'module-pch/report.json'
    elif pattern == ['Chromium local PCH comparison']:
        report_key = 'pch_experiment'
        report_path = 'local-pch/report.json'
    elif pattern in [['Chromium local compiler concurrency'], ['Chromium local compile pipeline']]:
        report_key = 'local_throughput'
        report_path = ('local-pipeline/report.json' if pattern == ['Chromium local compile pipeline']
                       else 'local-throughput/report.json')
    elif pattern == ['Chromium compiler preparation']:
        report_key = 'compiler_preparation'
        report_path = 'compiler-preparation/report.json'
    elif pattern in [['Chromium LLVM BOLT feasibility'], ['Chromium LLVM BOLT relocation preparation']]:
        report_key = 'compiler_preparation'
        report_path = 'llvm-bolt/report.json'
    elif pattern == ['Chromium representative LLVM compiler preparation']:
        report_key = 'compiler_preparation'
        report_path = 'llvm-compiler/report.json'
    elif pattern in [['Chromium compiler comparison'], ['Chromium representative compiler comparison']]:
        report_key = 'compiler_preparation'
        report_path = 'compiler-comparison/report.json'
    elif pattern in [['Chromium header include experiment'], ['Chromium private include experiment']]:
        report_key = 'include_experiment'
        report_path = 'private-includes/report.json'
    elif cold_prefix:
        report_key = 'cold_build'
        report_path = pattern[0].removeprefix(cold_prefix) + '/cold-build.json'
    if report_key:
        with api_request('GetInvocation', {
                'selector': {'invocation_id': identifier}, 'include_artifacts': True,
        }, os.environ['BUILDBUDDY_API_KEY']) as response:
            invocations = json.load(response).get('invocation', [])
        if report_key == 'cold_build':
            result['raw_event_artifacts'] = sum(
                artifact.get('name', '').endswith('/cold-events.json')
                for invocation in invocations for artifact in invocation.get('artifacts', []))
            profiles = [artifact for invocation in invocations
                        for artifact in invocation.get('artifacts', [])
                        if artifact.get('name', '').endswith(('/cold-profile.json', '/cold-profile.json.gz'))]
            if len(profiles) == 1:
                cold_profile = profiles[0]['uri']
        reports = [artifact for invocation in invocations
                   for artifact in invocation.get('artifacts', [])
                   if artifact.get('name', '').endswith('/' + report_path)
                   or artifact.get('name') == report_path]
        if len(reports) == 1:
            with api_request('GetFile', {'uri': reports[0]['uri']},
                             os.environ['BUILDBUDDY_API_KEY']) as response:
                payload = response.read(4 * 1024 * 1024 + 1)
            if len(payload) > 4 * 1024 * 1024:
                raise ValueError('Build measurement report exceeds 4 MiB')
            result[report_key] = json.loads(payload)
            if report_key == 'pch_experiment' and not result[report_key].get('complete'):
                phase = result[report_key].get('active_phase')
                if phase in {'warmup-baseline', 'warmup-candidate', 'baseline-1', 'baseline-2',
                             'candidate-1', 'candidate-2'}:
                    path = report_path.removesuffix('report.json') + phase + '.profile.gz'
                    profiles = [artifact for invocation in invocations
                                for artifact in invocation.get('artifacts', [])
                                if artifact.get('name', '').endswith('/' + path) or artifact.get('name') == path]
                    if len(profiles) == 1:
                        with api_request('GetFile', {'uri': profiles[0]['uri']},
                                         os.environ['BUILDBUDDY_API_KEY']) as response:
                            result['incomplete_pch_profile'] = {
                                'phase': phase, 'summary': trace_summary(_ProfileDownload(response), allow_partial=True)}
        if report_key == 'cold_build':
            resource_path = report_path.removesuffix('cold-build.json') + 'cold-resources.jsonl'
            resources = [artifact for invocation in invocations
                         for artifact in invocation.get('artifacts', [])
                         if artifact.get('name', '').endswith('/' + resource_path)
                         or artifact.get('name') == resource_path]
            if len(resources) == 1:
                with api_request('GetFile', {'uri': resources[0]['uri']},
                                 os.environ['BUILDBUDDY_API_KEY']) as response:
                    payload = response.read(16 * 1024 * 1024 + 1)
                if len(payload) > 16 * 1024 * 1024:
                    raise ValueError('Resource samples exceed 16 MiB')
                lines = payload.splitlines(keepends=True)
                result['cold_resource_samples'] = [json.loads(line) for line in lines if line.endswith(b'\n')]
                result['cold_resource_log_complete'] = not payload or payload.endswith(b'\n')
        if report_key == 'cold_build':
            summary_path = report_path.removesuffix('cold-build.json') + 'trace-summary.json'
            summaries = [artifact for invocation in invocations
                         for artifact in invocation.get('artifacts', [])
                         if artifact.get('name', '').endswith('/' + summary_path)
                         or artifact.get('name') == summary_path]
            if len(summaries) == 1:
                with api_request('GetFile', {'uri': summaries[0]['uri']},
                                 os.environ['BUILDBUDDY_API_KEY']) as response:
                    payload = response.read(MAX_TRACE_SUMMARY_BYTES + 1)
                if len(payload) > MAX_TRACE_SUMMARY_BYTES:
                    raise ValueError('Profile summary exceeds 32 MiB')
                result['cold_profile'] = json.loads(payload)
    for child in outer.get('childInvocations', []):
        child_id = child['invocationId']
        full = rpc('GetInvocation', {'lookup': {'invocationId': child_id}})['invocation'][0]
        summary = summarize(full)
        for profile in summary['profiles']:
            request = urllib.request.Request(
                API_URL + 'GetFile', data=json.dumps({'uri': profile['uri']}).encode(),
                headers={'Content-Type': 'application/json',
                         'x-buildbuddy-api-key': os.environ['BUILDBUDDY_API_KEY']})
            with urllib.request.urlopen(request, timeout=120) as response:
                profile['summary'] = trace_summary(_ProfileDownload(response))
            del profile['uri']
        result['children'].append(summary)
    if cold_profile and 'cold_profile' not in result and not any(child['profiles'] for child in result['children']):
        with api_request('GetFile', {'uri': cold_profile}, os.environ['BUILDBUDDY_API_KEY']) as response:
            result['cold_profile'] = trace_summary(_ProfileDownload(response), allow_partial=True)
    if cold_prefix == 'Chromium strict cold build ':
        result['strict_cold_timing_verified'] = strict_cold_timing_verified(
            outer, result.get('cold_build', {}))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9a-f]{40}', args.revision):
        parser.error('--revision must be a full commit SHA')
    repository = os.environ.get('GITHUB_REPOSITORY', 'formatjs/chromium')
    request = urllib.request.Request(
        f'https://api.github.com/repos/{repository}/commits/{args.revision}/status?per_page=100',
        headers={'Authorization': 'Bearer ' + os.environ['GH_TOKEN']})
    with urllib.request.urlopen(request, timeout=60) as response:
        statuses = json.load(response)['statuses']
    identifiers = {}
    for status in statuses:
        url = status.get('target_url', '')
        if url.startswith('https://formatjs.buildbuddy.io/invocation/'):
            identifiers.setdefault(status['context'], invocation_id(url))
    args.directory.mkdir(parents=True, exist_ok=True)
    # Full cold traces retain large decoded event graphs.
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {name: executor.submit(collect, identifier)
                   for name, identifier in identifiers.items()}
        results = {}
        for name, future in futures.items():
            try:
                results[name] = future.result()
            except Exception as error:
                results[name] = {'error': str(error)}
            (args.directory / 'report.json').write_text(json.dumps({
                'revision': args.revision, 'workflows': results}, indent=2) + '\n')
            print(name + ': ' + ('ERROR ' + results[name]['error'] if 'error' in results[name]
                                else str(len(results[name]['children'])) + ' Bazel invocations'), flush=True)
    if any('error' in result for result in results.values()):
        raise RuntimeError('Some BuildBuddy profiles could not be collected; see report.json')


if __name__ == '__main__':
    main()
