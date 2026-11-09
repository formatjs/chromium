from contextlib import redirect_stderr
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tools.ci.local_cold import NORMAL_PROJECT_PCH_NAMES, eager_template_pch_producers, local_cold_report, main
from tools.ci.bb_cold import main as bb_main


class LocalColdBuildTest(unittest.TestCase):
    def test_eager_manifest_identifies_producers_and_rejects_invalid_entries(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary)
            self.assertEqual(eager_template_pch_producers(source), frozenset())
            manifest = source / 'overlays/chromium/bcr/overlay/native/eager_template_pch_data.bzl'
            manifest.parent.mkdir(parents=True)
            manifest.write_text('EAGER_TEMPLATE_SOURCES = {}\n')
            self.assertEqual(eager_template_pch_producers(source), frozenset())
            mapping = {'base_bind_default_pch': {'a': ['one.cc', 'two.cc'], 'b': ['three.cc']},
                       'base_bind_complete_pch': {'c': ['four.cc']}}
            manifest.write_text('EAGER_TEMPLATE_SOURCES = ' + repr(mapping) + '\n')
            self.assertEqual(eager_template_pch_producers(source),
                             {'base_bind_default_pch', 'base_bind_complete_pch'})
            for invalid in [[], {'base_bind_default_pch': {}}, {'base_bind_default_pch': {'a': []}},
                            {'base_bind_default_pch': {'a': [None]}}, {'unknown': {'a': ['one.cc']}}]:
                manifest.write_text('EAGER_TEMPLATE_SOURCES = ' + repr(invalid) + '\n')
                with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                    eager_template_pch_producers(source)

    def test_base_bind_requires_project_pch_before_creating_build_state(self):
        command = ['cold-build', '--directory', '/unused-trial', '--revision', 'a' * 40,
                   '--base-bind-pch']
        for entrypoint, flags in [(bb_main, []), (main, ['--repository-cache', '/unused-cache',
                                                       '--bazel', '/unused-bazel'])]:
            error = io.StringIO()
            with self.subTest(entrypoint=entrypoint.__module__), mock.patch('sys.argv', command + flags), \
                    redirect_stderr(error):
                with self.assertRaises(SystemExit) as stopped:
                    entrypoint()
            self.assertEqual(stopped.exception.code, 2)
            self.assertIn('--base-bind-pch requires --project-pch', error.getvalue())

    def test_pch_requires_matching_native_linux_configuration(self):
        command = ['local-cold', '--directory', '/unused-trial', '--repository-cache', '/unused-cache',
                   '--revision', 'a' * 40, '--bazel', '/unused-bazel', '--blink-pch']
        for flags in [[], ['--native-tools', '--platform', 'linux-arm64']]:
            error = io.StringIO()
            with self.subTest(flags=flags), mock.patch('sys.argv', command + flags), redirect_stderr(error):
                with self.assertRaises(SystemExit) as stopped:
                    main()
            self.assertEqual(stopped.exception.code, 2)
            self.assertIn('--blink-pch requires --native-tools on linux-amd64', error.getvalue())

    def test_local_proof_requires_fresh_roots_canonical_disabling_and_real_sandboxes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cache, events = root.parent / 'fetch-cache', root / 'events.json'
            options = {
                'output_base': str(root / 'output-base'), 'install_base': str(root / 'install-base'),
                'output_user_root': str(root / 'bazel-root'), 'repository_cache': str(cache),
                'bazelrc': str(root / 'source/.bazelrc'), 'batch': '1',
                'system_rc': '0', 'home_rc': '0', 'workspace_rc': '0',
                'remote_executor': '', 'remote_cache': '', 'disk_cache': '', 'repo_contents_cache': '',
                'remote_accept_cached': 'false', 'remote_upload_local_results': '0',
                'use_action_cache': '0', 'spawn_strategy': 'linux-sandbox',
                'remote_header': 'DO_NOT_EXPORT',
            }

            command = ['/verified-bazel', '--nosystem_rc', '--nohome_rc', '--noworkspace_rc',
                       '--bazelrc=' + str(root / 'source/.bazelrc'), 'build']

            def measure(changes=None, runners=None, fresh=True, success=True, compiles=16, client_command=None,
                        expected_pch_count=0, pch_count=0, validator_count=0,
                        expected_prefix_count=0, prefix_count=0, base_bind_pch=False, eager_pchs=0, omitted_original=(), mutate_pch_files=None):
                values = options | (changes or {})
                records = [
                    {'structuredCommandLine': {'commandLineLabel': 'canonical', 'sections': [{
                        'sectionLabel': 'startup options', 'optionList': {'option': [
                            {'optionName': name, 'optionValue': value} for name, value in values.items()
                            if value is not None
                        ]}}]}},
                    {'buildMetrics': {'actionSummary': {
                        'actionData': [{'mnemonic': 'CppCompile', 'actionsExecuted': str(compiles)},
                                       {'mnemonic': 'ChromiumProjectPch', 'actionsExecuted': str(pch_count)},
                                       {'mnemonic': 'ChromiumPchClosure', 'actionsExecuted': str(validator_count)},
                                       {'mnemonic': 'ChromiumPchPrefix', 'actionsExecuted': str(prefix_count)}],
                        'runnerCount': runners if runners is not None else [
                            {'name': 'linux-sandbox', 'count': compiles}, {'name': 'internal', 'count': 2}],
                    }}},
                ]
                events.write_text('\n'.join(json.dumps(record) for record in records))
                eager_producers = tuple(sorted(NORMAL_PROJECT_PCH_NAMES))[:eager_pchs]
                native = root / ('output-base/execroot/_main/bazel-out/k8-fastbuild/bin/'
                                 'external/+chromium_dependencies+chromium/native')
                native.mkdir(parents=True, exist_ok=True)
                for path in native.glob('*.pch'):
                    path.unlink()
                if eager_producers:
                    produced = (NORMAL_PROJECT_PCH_NAMES - set(omitted_original)
                                | {name + '_templates' for name in eager_producers})
                    for name in produced:
                        for suffix in ['.raw.pch', '.pch']:
                            (native / (name + suffix)).write_bytes(('fixture:' + name).encode())
                if mutate_pch_files:
                    mutate_pch_files(native)
                result = local_cold_report(events, 500, success, root, cache, fresh,
                                           command if client_command is None else client_command,
                                           expected_pch_count=expected_pch_count,
                                           expected_prefix_count=expected_prefix_count,
                                           expected_base_bind_pch=base_bind_pch,
                                           expected_eager_producers=eager_producers)
                self.assertNotIn('DO_NOT_EXPORT', json.dumps(result))
                return result

            result = measure()
            self.assertTrue(result['cold_result_verified'])
            self.assertTrue(result['local_execution_verified'])
            self.assertTrue(measure(expected_pch_count=6, pch_count=6, validator_count=6)['cold_result_verified'])
            self.assertTrue(measure(expected_pch_count=7, pch_count=7, validator_count=7,
                                    expected_prefix_count=1, prefix_count=1)['cold_result_verified'])
            self.assertTrue(measure({'define': 'CHROMIUM_BASE_BIND_PCH=1'}, base_bind_pch=True,
                                    pch_count=12, validator_count=12, prefix_count=1)['cold_result_verified'])
            self.assertTrue(measure({'define': 'CHROMIUM_BASE_BIND_PCH=1'}, base_bind_pch=True,
                                    eager_pchs=2, pch_count=14, validator_count=14,
                                    prefix_count=1)['cold_result_verified'])
            pruned = measure({'define': 'CHROMIUM_BASE_BIND_PCH=1'}, base_bind_pch=True,
                             eager_pchs=2, pch_count=13, validator_count=13, prefix_count=1,
                             omitted_original=['base_bind_default_pch'])
            self.assertTrue(pruned['cold_result_verified'])
            self.assertEqual(pruned['pch_output_proof']['unused_original'], ['base_bind_default_pch'])
            eager_name = sorted(NORMAL_PROJECT_PCH_NAMES)[0] + '_templates'
            mutations = {
                'missing_eager': lambda folder: [(folder / (eager_name + suffix)).unlink()
                                                 for suffix in ['.raw.pch', '.pch']],
                'missing_validation': lambda folder: (folder / (eager_name + '.pch')).unlink(),
                'wrong_validation_bytes': lambda folder: (folder / (eager_name + '.pch')).write_bytes(
                    b'x' * (folder / (eager_name + '.pch')).stat().st_size),
                'unexpected_producer': lambda folder: [(folder / ('unexpected_pch' + suffix)).write_bytes(b'extra')
                                                       for suffix in ['.raw.pch', '.pch']],
            }
            for reason, mutation in mutations.items():
                with self.subTest(pch_files=reason):
                    invalid = measure({'define': 'CHROMIUM_BASE_BIND_PCH=1'}, base_bind_pch=True,
                                      eager_pchs=2, pch_count=13 if reason == 'missing_eager' else 15 if reason == 'unexpected_producer' else 14,
                                      validator_count=13 if reason == 'missing_eager' else 15 if reason == 'unexpected_producer' else 14,
                                      prefix_count=1, mutate_pch_files=mutation)
                    self.assertFalse(invalid['cold_result_verified'])
                    self.assertFalse(invalid['requested_pch_actions_verified'])
            for producers, validators in [(12, 12), (13, 14), (14, 13), (15, 15)]:
                with self.subTest(eager_producers=producers, eager_validators=validators):
                    invalid = measure({'define': 'CHROMIUM_BASE_BIND_PCH=1'}, base_bind_pch=True,
                                      eager_pchs=2, pch_count=producers, validator_count=validators,
                                      prefix_count=1)
                    self.assertFalse(invalid['cold_result_verified'])
                    self.assertFalse(invalid['requested_pch_actions_verified'])
            self.assertFalse(measure(expected_pch_count=2, pch_count=2, validator_count=2,
                                     eager_pchs=2)['cold_result_verified'])
            for define, producers, validators, prefixes in [
                (None, 12, 12, 1), ('CHROMIUM_BASE_BIND_PCH=0', 12, 12, 1),
                ('CHROMIUM_BASE_BIND_PCH=1', 10, 10, 1), ('CHROMIUM_BASE_BIND_PCH=1', 11, 12, 1),
                ('CHROMIUM_BASE_BIND_PCH=1', 12, 11, 1), ('CHROMIUM_BASE_BIND_PCH=1', 13, 13, 1),
                ('CHROMIUM_BASE_BIND_PCH=1', 12, 12, 0),
            ]:
                with self.subTest(define=define, producers=producers, validators=validators, prefixes=prefixes):
                    invalid = measure({'define': define}, base_bind_pch=True, pch_count=producers,
                                      validator_count=validators, prefix_count=prefixes)
                    self.assertFalse(invalid['cold_result_verified'])
                    self.assertFalse(invalid['requested_pch_actions_verified'])
            for count in [0, 2]:
                with self.subTest(prefix_count=count):
                    invalid = measure(expected_pch_count=7, pch_count=7, validator_count=7,
                                      expected_prefix_count=1, prefix_count=count)
                    self.assertFalse(invalid['cold_result_verified'])
                    self.assertFalse(invalid['requested_pch_actions_verified'])
            self.assertFalse(measure(prefix_count=1)['cold_result_verified'])
            for pch_count, validator_count in [(0, 0), (6, 0), (0, 6), (5, 6), (7, 6), (6, 5), (6, 7)]:
                with self.subTest(pch_count=pch_count, validator_count=validator_count):
                    missing = measure(expected_pch_count=6, pch_count=pch_count, validator_count=validator_count)
                    self.assertFalse(missing['cold_result_verified'])
                    self.assertFalse(missing['local_execution_verified'])
            self.assertNotIn('actionCacheStatistics', result['build_metrics']['actionSummary'])
            self.assertTrue(measure({'system_rc': None, 'home_rc': None, 'workspace_rc': None,
                                     'bazelrc': None})['cold_result_verified'])
            for changes in [
                {'remote_executor': 'grpcs://worker'}, {'remote_cache': 'grpcs://cache'},
                {'use_action_cache': 'true'}, {'use_action_cache': None}, {'spawn_strategy': 'local'},
                {'repo_contents_cache': '/retained-repositories'}, {'disk_cache': '/retained-results'},
                {'output_base': '/retained-output'}, {'install_base': '/retained-install'},
                {'home_rc': '1'}, {'batch': '0'}, {'repository_cache': '/unexpected-cache'},
            ]:
                with self.subTest(changes=changes):
                    self.assertFalse(measure(changes)['cold_result_verified'])
            for settings in [
                {'fresh': False}, {'success': False}, {'compiles': 0},
                {'runners': [{'name': 'remote', 'count': 16}]},
                {'runners': [{'name': 'linux-sandbox', 'count': 16}, {'name': 'action cache hit', 'count': 1}]},
                {'client_command': []},
                {'client_command': [*command[:-1], '--home_rc', 'build']},
            ]:
                with self.subTest(settings=settings):
                    self.assertFalse(measure(**settings)['cold_result_verified'])


if __name__ == '__main__':
    unittest.main()
