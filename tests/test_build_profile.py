import gzip
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tools.ci import profile_buildbuddy
from tools.ci.profile_buildbuddy import compiler_work, summarize, trace_summary


class BuildProfileTest(unittest.TestCase):
    def test_local_subprocess_attribution_excludes_unrelated_threads_and_private_paths(self):
        events = [
            {'cat': 'action processing', 'ts': 0, 'dur': 10000000, 'tid': 1,
             'args': {'mnemonic': 'CppCompile', 'command': 'DO_NOT_EXPORT'}},
            {'cat': 'action processing', 'ts': 1000000, 'dur': 2000000, 'tid': 2,
             'out': 'private/gen/third_party/blink/renderer/bindings/core/v8/output.cc',
             'args': {'mnemonic': 'ChromiumPython'}},
            {'name': 'subprocess.run', 'ts': 1000000, 'dur': 8000000, 'tid': 1},
            {'name': 'sandbox.createFileSystem', 'ts': 0, 'dur': 500000, 'tid': 1},
            {'name': 'subprocess.run', 'ts': 1100000, 'dur': 1500000, 'tid': 2},
            {'name': 'subprocess.run', 'ts': 1000000, 'dur': 1000000, 'tid': 3},
            {'name': 'subprocess.run', 'ts': 11000000, 'dur': 1000000, 'tid': 1},
        ]
        result = profile_buildbuddy.local_action_work(events)
        self.assertEqual(result['CppCompile'], {'action_spans': 1, 'action_task_seconds': 10,
                                              'max_action_seconds': 10, 'subprocess_task_seconds': 8,
                                              'sandbox_task_seconds': 0.5})
        self.assertEqual(result['BlinkBindings']['subprocess_task_seconds'], 1.5)
        self.assertNotIn('DO_NOT_EXPORT', json.dumps(result))
        self.assertNotIn('private/', json.dumps(result))

    def test_strict_cold_timing_requires_complete_outer_workflow_within_hour(self):
        outer = {'success': True, 'invocationStatus': 'COMPLETE_INVOCATION_STATUS',
                 'durationUsec': '3550000000'}
        report = {'cold_result_verified': True, 'local_execution_verified': True,
                  'elapsed_seconds': 3500}
        self.assertTrue(profile_buildbuddy.strict_cold_timing_verified(outer, report))
        for change in [{'durationUsec': '3600000000'}, {'durationUsec': None},
                       {'durationUsec': '3499000000'}, {'success': False},
                       {'invocationStatus': 'PARTIAL_INVOCATION_STATUS'}]:
            with self.subTest(change=change):
                self.assertFalse(profile_buildbuddy.strict_cold_timing_verified(outer | change, report))
        for change in [{'cold_result_verified': False}, {'local_execution_verified': False},
                       {'elapsed_seconds': 3600}, {'elapsed_seconds': float('nan')}]:
            with self.subTest(change=change):
                self.assertFalse(profile_buildbuddy.strict_cold_timing_verified(outer, report | change))

    def test_strict_cold_profile_collects_published_summary_without_raw_trace(self):
        report = {'cold_result_verified': True, 'local_execution_verified': True, 'elapsed_seconds': 3500}
        summary = {'trace_complete': True, 'event_count': 1200,
                   'compiler_work': {'v8': {'compile_spans': 90}}}
        report_uri = 'bytestream://formatjs.buildbuddy.io/cold-report'
        summary_uri = 'bytestream://formatjs.buildbuddy.io/trace-summary'
        outer = {'pattern': ['Chromium strict cold build linux-amd64'], 'success': True,
                 'invocationStatus': 'COMPLETE_INVOCATION_STATUS', 'durationUsec': '3550000000'}
        artifacts = {'invocation': [{'artifacts': [
            {'name': 'command-0/linux-amd64/cold-build.json', 'uri': report_uri},
            {'name': 'command-0/linux-amd64/trace-summary.json', 'uri': summary_uri}]}]}
        with mock.patch.object(profile_buildbuddy, 'rpc', return_value={'invocation': [outer]}), \
                mock.patch.object(profile_buildbuddy, 'api_request', side_effect=[
                    io.BytesIO(json.dumps(artifacts).encode()), io.BytesIO(json.dumps(report).encode()),
                    io.BytesIO(json.dumps(summary).encode())]) as api, \
                mock.patch.dict(os.environ, {'BUILDBUDDY_API_KEY': 'read-only-test-key'}):
            result = profile_buildbuddy.collect('workflow')
        self.assertEqual(result['cold_build'], report)
        self.assertEqual(result['cold_profile'], summary)
        self.assertTrue(result['strict_cold_timing_verified'])
        self.assertEqual(api.call_args_list, [
            mock.call('GetInvocation', {'selector': {'invocation_id': 'workflow'},
                                       'include_artifacts': True}, 'read-only-test-key'),
            mock.call('GetFile', {'uri': report_uri}, 'read-only-test-key'),
            mock.call('GetFile', {'uri': summary_uri}, 'read-only-test-key'),
        ])

    def test_compiler_experiment_report_is_collected_from_workflow_artifact(self):
        report = {'baseline': {'input_entries': 76130}, 'include-scan': {'input_entries': 1000}}
        uri = 'bytestream://formatjs.buildbuddy.io/report'
        for pattern, artifact_path, key in [
            ('Chromium compile input experiment', 'compile-input-experiment/report.json', 'compile_experiment'),
            ('Chromium compile inputs host-blink', 'compile-input-experiment/report.json', 'compile_experiment'),
            ('Chromium cold build linux-amd64', 'linux-amd64/cold-build.json', 'cold_build'),
            ('Chromium clean cold build darwin-arm64', 'darwin-arm64/cold-build.json', 'cold_build'),
            ('Chromium compression benchmark windows-amd64', 'compression-experiment/report.json', 'compression_experiment'),
            ('Chromium bindings budget darwin-arm64', 'bindings-budget/report.json', 'bindings_experiment'),
            ('Chromium Clang phase profile', 'clang-profile/report.json', 'clang_experiment'),
            ('Chromium local compiler concurrency', 'local-throughput/report.json', 'local_throughput'),
            ('Chromium local PCH comparison', 'local-pch/report.json', 'pch_experiment'),
            ('Chromium module PCH comparison', 'module-pch/report.json', 'pch_experiment'),
            ('Chromium compiler preparation', 'compiler-preparation/report.json', 'compiler_preparation'),
            ('Chromium compiler comparison', 'compiler-comparison/report.json', 'compiler_preparation'),
            ('Chromium header include experiment', 'private-includes/report.json', 'include_experiment'),
            ('Chromium private include experiment', 'private-includes/report.json', 'include_experiment'),
        ]:
            with self.subTest(pattern=pattern):
                outer = {'pattern': [pattern]}
                artifacts = {'invocation': [{'artifacts': [{
                    'name': 'command-0/' + artifact_path, 'uri': uri}]}]}
                with mock.patch.object(profile_buildbuddy, 'rpc', return_value={'invocation': [outer]}), \
                        mock.patch.object(profile_buildbuddy, 'api_request', side_effect=[
                            io.BytesIO(json.dumps(artifacts).encode()), io.BytesIO(json.dumps(report).encode())]) as api, \
                        mock.patch.dict(os.environ, {'BUILDBUDDY_API_KEY': 'read-only-test-key'}):
                    result = profile_buildbuddy.collect('workflow')
                self.assertEqual(result[key], report)
                api.assert_has_calls([
                    mock.call('GetInvocation', {'selector': {'invocation_id': 'workflow'},
                                               'include_artifacts': True}, 'read-only-test-key'),
                    mock.call('GetFile', {'uri': uri}, 'read-only-test-key'),
                ])

    def test_killed_cold_run_keeps_sanitized_completed_trace_events(self):
        event = {'cat': 'general information', 'name': 'MerkleTreeComputer.buildForSpawn',
                 'ph': 'X', 'dur': 500000, 'args': {'command': 'DO_NOT_EXPORT'}}
        trace = '{"otherData":{},"traceEvents":[\n' + json.dumps(event) + ',\n{"unfinished":'
        uri = 'bytestream://formatjs.buildbuddy.io/cold-profile'
        outer = {'pattern': ['Chromium cold build linux-amd64'],
                 'success': False, 'invocationStatus': 'COMPLETE_INVOCATION_STATUS'}
        artifacts = {'invocation': [{'artifacts': [{
            'name': 'command-0/linux-amd64/cold-profile.json', 'uri': uri},
            {'name': 'command-0/linux-amd64/cold-events.json', 'uri': 'DO_NOT_DOWNLOAD'}]}]}
        with mock.patch.object(profile_buildbuddy, 'rpc', return_value={'invocation': [outer]}), \
                mock.patch.object(profile_buildbuddy, 'api_request', side_effect=[
                    io.BytesIO(json.dumps(artifacts).encode()), io.BytesIO(trace.encode())]), \
                mock.patch.dict(os.environ, {'BUILDBUDDY_API_KEY': 'read-only-test-key'}):
            result = profile_buildbuddy.collect('killed-workflow')
        self.assertEqual(result['raw_event_artifacts'], 1)
        self.assertFalse(result['cold_profile']['trace_complete'])
        self.assertEqual(result['cold_profile']['event_count'], 1)
        self.assertEqual(result['cold_profile']['tasks']['merkle'],
                         {'count': 1, 'task_seconds': 0.5})
        self.assertNotIn('cold_build', result)
        self.assertNotIn('DO_NOT_EXPORT', json.dumps(result))
        self.assertNotIn(uri, json.dumps(result))

    def test_incomplete_profiles_require_explicit_diagnostic_mode(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'partial.json'
            path.write_text('{"traceEvents":[{"ph":"X","dur":1},')
            with self.assertRaises(json.JSONDecodeError):
                trace_summary(path)
            self.assertFalse(trace_summary(path, allow_partial=True)['trace_complete'])
            for content in ['{} garbage', '{"traceEvents":[{"unfinished":']:
                path.write_text(content)
                with self.assertRaises(ValueError):
                    trace_summary(path, allow_partial=True)

    def test_compiler_attribution_respects_threads_intervals_and_generated_sources(self):
        events = [
            {'cat': 'action processing', 'name': 'Compiling native/gen/third_party/blink/a.cc [for tool]',
             'ph': 'X', 'tid': 1, 'ts': 0, 'dur': 10000000},
            {'cat': 'action processing', 'name': 'Compiling components/b.cc',
             'ph': 'X', 'tid': 2, 'ts': 0, 'dur': 10000000},
            {'cat': 'action processing', 'name': 'Compiling DO_NOT_EXPORT',
             'ph': 'X', 'tid': 3, 'ts': 0, 'dur': 10000000},
            *[{'cat': 'general information', 'name': 'MerkleTreeComputer.buildForSpawn',
               'ph': 'X', 'tid': thread, 'ts': 100, 'dur': duration}
              for thread, duration in [(1, 1000000), (2, 2000000), (99, 5000000)]],
            {'cat': 'Remote execution process wall time', 'ph': 'X',
             'tid': 1, 'ts': 2000000, 'dur': 3000000},
            {'cat': 'Remote execution process wall time', 'ph': 'X',
             'tid': 2, 'ts': 9000000, 'dur': 3000000},
            {'cat': 'discover inputs', 'ph': 'X', 'tid': 1, 'ts': 100, 'dur': 500000},
            {'cat': 'include scanner', 'ph': 'X', 'tid': 1, 'ts': 200, 'dur': 250000},
        ]
        result = compiler_work(events)
        self.assertEqual(result['blink']['compile_spans'], 1)
        self.assertEqual(result['blink']['tool_compile_spans'], 1)
        self.assertEqual(result['blink']['merkle_task_seconds'], 1)
        self.assertEqual(result['blink']['worker_task_seconds'], 3)
        self.assertEqual(result['blink']['input_discovery_task_seconds'], 0.5)
        self.assertEqual(result['blink']['include_scanning_task_seconds'], 0.25)
        self.assertEqual(result['components']['merkle_task_seconds'], 2)
        self.assertEqual(result['components']['worker_task_seconds'], 0)
        self.assertNotIn('DO_NOT_EXPORT', json.dumps(result))

    def test_metrics_preserved_without_command_credentials(self):
        metrics = {'actionSummary': {'actionsCreated': '42123', 'actionsExecuted': '17'},
                   'timingMetrics': {'wallTimeInMs': '12345'}}
        result = summarize({
            'invocationId': 'build', 'command': 'build',
            'structuredCommandLine': [{'secret': 'DO_NOT_EXPORT'}],
            'event': [
                {'buildEvent': {'buildMetrics': metrics}},
                {'buildEvent': {'buildToolLogs': {'log': [
                    {'name': 'command.profile.gz', 'uri': 'bytestream://formatjs.buildbuddy.io/profile'},
                    {'name': 'other.log', 'contents': 'DO_NOT_EXPORT'},
                ]}}},
            ],
        })
        self.assertEqual(result['metrics'], [metrics])
        self.assertEqual(result['profiles'], [
            {'name': 'command.profile.gz', 'uri': 'bytestream://formatjs.buildbuddy.io/profile'}])
        self.assertNotIn('DO_NOT_EXPORT', json.dumps(result))

    def test_trace_summary_keeps_durations_and_phases_without_event_arguments(self):
        events = [
            {'name': 'PRIVATE_SOURCE_NAME', 'cat': 'action processing', 'ph': 'X', 'ts': 10, 'dur': 40,
             'args': {'command': 'DO_NOT_EXPORT'}},
            {'name': 'analysis', 'cat': 'build phase marker', 'ph': 'X', 'ts': 0, 'dur': 10},
            {'name': 'counter', 'ph': 'C', 'ts': 1, 'dur': 9999},
        ]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'trace.gz'
            with gzip.open(path, 'wt') as output:
                json.dump({'traceEvents': events}, output)
            result = trace_summary(path)
        self.assertEqual([item['dur'] for item in result['longest_events']], [40, 10])
        self.assertEqual([item['dur'] for item in result['phases']], [10])
        self.assertNotIn('DO_NOT_EXPORT', json.dumps(result))
        self.assertNotIn('PRIVATE_SOURCE_NAME', json.dumps(result))

    def test_trace_summary_preserves_instant_phases_and_selected_resource_samples(self):
        events = [
            {'cat': 'build phase marker', 'name': 'Complete build', 'ph': 'i', 'ts': 9000000},
            {'cat': 'general information', 'name': 'MerkleTreeComputer.buildForSpawn',
             'ph': 'X', 'dur': 500000},
            {'cat': 'Remote execution process wall time', 'ph': 'X', 'dur': 2000000},
            *[{'name': 'CPU usage (Bazel)', 'ph': 'C',
               'args': {'cpu': value, 'command': 'DO_NOT_EXPORT'}} for value in (2, 6)],
            {'name': 'Memory usage (Bazel)', 'ph': 'C', 'args': {'memory': 1024}},
        ]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'trace.json'
            path.write_text(json.dumps({'traceEvents': events}))
            result = trace_summary(path)
        self.assertEqual(result['phases'][0]['name'], 'Complete build')
        self.assertEqual(result['phases'][0]['ph'], 'i')
        self.assertEqual(result['tasks']['merkle'], {'count': 1, 'task_seconds': 0.5})
        self.assertEqual(result['tasks']['worker_execution'], {'count': 1, 'task_seconds': 2})
        self.assertEqual(result['counters']['bazel_cpu'], {
            'samples': 2, 'sample_mean': 4, 'sample_max': 6, 'unit': 'cores'})
        self.assertNotIn('DO_NOT_EXPORT', json.dumps(result))


if __name__ == '__main__':
    unittest.main()
