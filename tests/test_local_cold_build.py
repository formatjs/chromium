from contextlib import redirect_stderr
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tools.ci.local_cold import (NORMAL_PROJECT_PCH_NAMES, eager_template_pch_producers,
                               local_cold_report, main, pch_output_proof, serialization_pch_producers, shared_pch_producers, v8_objects_pch_producers)
from tools.ci.bb_cold import main as bb_main


class LocalColdBuildTest(unittest.TestCase):
    def test_pch_proof_checks_every_pair_and_rejects_invalid_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            native = directory / ('output-base/execroot/_main/bazel-out/k8-fastbuild/bin/'
                                  'external/+chromium_dependencies+chromium/native')
            native.mkdir(parents=True)
            self.assertTrue(pch_output_proof(directory, ())['verified'])
            names = tuple('shared_test_' + str(index) for index in range(17))
            for name in names:
                for suffix in ('.raw.pch', '.pch'):
                    (native / (name + suffix)).write_bytes(name.encode())
            self.assertTrue(pch_output_proof(directory, (), names)['verified'])
            for index, name in enumerate(names):
                validated = native / (name + '.pch')
                validated.write_bytes(b'x' * len(name))
                with self.subTest(corrupt_pair=index):
                    self.assertFalse(pch_output_proof(directory, (), names)['verified'])
                validated.write_bytes(name.encode())
            raw = native / (names[-1] + '.raw.pch')
            raw.write_bytes(b'')
            self.assertFalse(pch_output_proof(directory, (), names)['verified'])
            raw.write_bytes(names[-1].encode())
            validated = native / (names[-1] + '.pch')
            validated.unlink()
            validated.symlink_to(raw)
            self.assertFalse(pch_output_proof(directory, (), names)['verified'])

    def test_shared_mode_requires_existing_pch_configuration_before_setup(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / 'build'
            arguments = ['local_cold', '--directory', str(directory),
                         '--repository-cache', str(Path(temporary) / 'fetch-cache'),
                         '--revision', 'a' * 40, '--bazel', '/verified-bazel', '--shared-pch']
            with mock.patch('sys.argv', arguments), redirect_stderr(io.StringIO()) as errors, self.assertRaises(SystemExit):
                main()
            self.assertIn('--shared-pch requires --base-bind-pch', errors.getvalue())
            self.assertFalse(directory.exists())

    def test_shared_manifest_requires_qualified_local_producer_names(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary)
            manifest = source / 'overlays/chromium/bcr/overlay/native/qualified_shared_prefixes.bzl'
            manifest.parent.mkdir(parents=True)
            for invalid in [{}, [], {'owner': {}}, {'owner': {'a.cc': '@elsewhere//:prebuilt'}},
                            {'owner': {'a.cc': ':shared_unknown_eager_pch'}}]:
                manifest.write_text('SHARED_PREFIX_IMPORTS = ' + repr(invalid) + '\n')
                with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                    shared_pch_producers(source)
            manifest.write_text('SHARED_PREFIX_IMPORTS = '+repr({'owner': {'a.cc': ':shared_sdk_0_eager_pch',
                                                                         'b.cc': ':shared_sdk_0_eager_pch'}})+'\n')
            self.assertEqual(shared_pch_producers(source), {'shared_sdk_0_eager_pch'})

    def test_nonpositive_limits_rejected_before_build_state_is_created(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / 'build'
            for option, seconds in [('--target-seconds', '0'), ('--target-seconds', '-1'),
                                    ('--jvm-processors', '0'), ('--jvm-processors', '-1')]:
                arguments = ['local_cold', '--directory', str(directory),
                             '--repository-cache', str(Path(temporary) / 'fetch-cache'),
                             '--revision', 'a' * 40, '--bazel', '/verified-bazel',
                             option, seconds]
                with self.subTest(option=option, value=seconds), mock.patch('sys.argv', arguments), \
                        redirect_stderr(io.StringIO()) as errors, self.assertRaises(SystemExit) as exit:
                    main()
                self.assertEqual(exit.exception.code, 2)
                self.assertIn(option + ' must be positive', errors.getvalue())
                self.assertFalse(directory.exists())

    def test_v8_manifest_requires_eager_subset_and_only_used_variants(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary)
            self.assertEqual(v8_objects_pch_producers(source), frozenset())
            manifest = source / 'overlays/chromium/bcr/overlay/native/v8_objects_pch_data.bzl'
            manifest.parent.mkdir(parents=True)
            for sources, eager, expected in [
                ({}, {}, set()),
                ({'owner': ['one.cc']}, {}, {'v8_objects_normal_pch'}),
                ({'owner': ['one.cc']}, {'owner': ['one.cc']}, {'v8_objects_eager_pch'}),
                ({'owner': ['one.cc', 'two.cc']}, {'owner': ['one.cc']},
                 {'v8_objects_normal_pch', 'v8_objects_eager_pch'}),
            ]:
                manifest.write_text('V8_OBJECTS_SOURCES = ' + repr(sources) + '\n'
                                    + 'V8_OBJECTS_EAGER_SOURCES = ' + repr(eager) + '\n')
                with self.subTest(sources=sources, eager=eager):
                    self.assertEqual(v8_objects_pch_producers(source), expected)
            for sources, eager in [([], {}), ({'owner': []}, {}),
                                   ({'owner': ['one.cc']}, {'other': ['one.cc']}),
                                   ({'owner': ['one.cc']}, {'owner': ['two.cc']}),
                                   ({'owner': [None]}, {}), ({}, {'owner': ['one.cc']})]:
                manifest.write_text('V8_OBJECTS_SOURCES = ' + repr(sources) + '\n'
                                    + 'V8_OBJECTS_EAGER_SOURCES = ' + repr(eager) + '\n')
                with self.subTest(sources=sources, eager=eager), self.assertRaises(ValueError):
                    v8_objects_pch_producers(source)
            for text in ['V8_OBJECTS_SOURCES = {}\n',
                         'V8_OBJECTS_SOURCES = {}\nV8_OBJECTS_SOURCES = {}\nV8_OBJECTS_EAGER_SOURCES = {}\n']:
                manifest.write_text(text)
                with self.subTest(text=text), self.assertRaises(ValueError):
                    v8_objects_pch_producers(source)

    def test_serialization_manifest_requires_valid_nonempty_routes(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary)
            self.assertEqual(serialization_pch_producers(source), frozenset())
            manifest = source / 'overlays/chromium/bcr/overlay/native/serialization_pch_data.bzl'
            manifest.parent.mkdir(parents=True)
            for mapping, expected in [({}, set()), ({'owner': ['source.cc']}, {'serialization_eager_pch'})]:
                manifest.write_text('SERIALIZATION_SOURCES = ' + repr(mapping) + '\n')
                self.assertEqual(serialization_pch_producers(source), expected)
            for invalid in [[], {'owner': []}, {'owner': [None]}, {'': ['source.cc']}]:
                manifest.write_text('SERIALIZATION_SOURCES = ' + repr(invalid) + '\n')
                with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                    serialization_pch_producers(source)

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
                'experimental_inmemory_sandbox_stashes': 'false',
                'remote_header': 'DO_NOT_EXPORT',
            }

            command = ['/verified-bazel', '--nosystem_rc', '--nohome_rc', '--noworkspace_rc',
                       '--bazelrc=' + str(root / 'source/.bazelrc'), 'build']

            def measure(changes=None, runners=None, fresh=True, success=True, compiles=16, client_command=None,
                        expected_pch_count=0, pch_count=0, validator_count=0,
                        expected_prefix_count=0, prefix_count=0, base_bind_pch=False, eager_pchs=0,
                        additional_pchs=(), shared_pchs=(), omitted_original=(), mutate_pch_files=None,
                        elapsed=500, target_seconds=3600, repository_hardlinks=False, jvm_processors=None,
                        discard_analysis_cache=False):
                values = options | (changes or {})
                records = [
                    {'structuredCommandLine': {'commandLineLabel': 'canonical', 'sections': [{
                        'sectionLabel': 'startup options', 'optionList': {'option': [
                            {'optionName': name, 'optionValue': item} for name, value in values.items()
                            if value is not None for item in (value if isinstance(value, list) else [value])
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
                if eager_producers or additional_pchs or shared_pchs:
                    produced = (NORMAL_PROJECT_PCH_NAMES - set(omitted_original)
                                | {name + '_templates' for name in eager_producers} | set(additional_pchs) | set(shared_pchs))
                    for name in produced:
                        for suffix in ['.raw.pch', '.pch']:
                            (native / (name + suffix)).write_bytes(('fixture:' + name).encode())
                if mutate_pch_files:
                    mutate_pch_files(native)
                result = local_cold_report(events, elapsed, success, root, cache, fresh,
                                           command if client_command is None else client_command,
                                           expected_pch_count=expected_pch_count,
                                           expected_prefix_count=expected_prefix_count,
                                           expected_base_bind_pch=base_bind_pch,
                                           expected_eager_producers=eager_producers,
                                           expected_additional_producers=additional_pchs,
                                           expected_shared_producers=shared_pchs,
                                           target_seconds=target_seconds,
                                           expected_repository_cache_hardlinks=repository_hardlinks,
                                           expected_jvm_processors=jvm_processors,
                                           expected_discard_analysis_cache=discard_analysis_cache)
                self.assertNotIn('DO_NOT_EXPORT', json.dumps(result))
                return result

            shared = ('shared_sdk_0_eager_pch', 'shared_global_plain_normal_pch')
            shared_flags = ['CHROMIUM_' + name + '=1' for name in
                            ['NATIVE_TOOLS', 'PROJECT_PCH', 'BLINK_PCH', 'BASE_BIND_PCH', 'SHARED_PCH']]
            shared_arguments = dict(base_bind_pch=True, shared_pchs=shared,
                                    omitted_original=NORMAL_PROJECT_PCH_NAMES,
                                    pch_count=2, validator_count=2, prefix_count=1)
            verified_shared = measure({'define': shared_flags}, **shared_arguments)
            self.assertTrue(verified_shared['cold_result_verified'])
            self.assertTrue(verified_shared['shared_pch_configuration_verified'])
            self.assertEqual(verified_shared['pch_output_proof']['unused_original'], sorted(NORMAL_PROJECT_PCH_NAMES))
            # Select the same eager producer ordering as the fixture.
            def prune_optional(native):
                for path in native.glob('*_templates*.pch'):
                    path.unlink()
                for suffix in ['.raw.pch', '.pch']:
                    (native / ('serialization_eager_pch' + suffix)).unlink()
            optional = measure({'define': shared_flags}, eager_pchs=2,
                               additional_pchs=('serialization_eager_pch',),
                               mutate_pch_files=prune_optional, **shared_arguments)
            self.assertTrue(optional['cold_result_verified'])
            for missing in shared_flags:
                self.assertFalse(measure({'define': [flag for flag in shared_flags if flag != missing]},
                                         **shared_arguments)['cold_result_verified'])
            def remove_shared(native):
                for suffix in ['.raw.pch', '.pch']:
                    (native / (shared[0] + suffix)).unlink()
            invalid_arguments = dict(shared_arguments, pch_count=1, validator_count=1)
            self.assertFalse(measure({'define': shared_flags}, mutate_pch_files=remove_shared,
                                     **invalid_arguments)['cold_result_verified'])
            self.assertFalse(measure({'define': shared_flags}, mutate_pch_files=lambda native:
                                     (native / (shared[0] + '.pch')).write_bytes(b'changed'),
                                     **shared_arguments)['cold_result_verified'])

            result = measure()
            self.assertTrue(result['cold_result_verified'])
            discard_command = command + ['--discard_analysis_cache=true']
            for value in ['true', '1']:
                verified_discard = measure({'discard_analysis_cache': value},
                                           client_command=discard_command, discard_analysis_cache=True)
                self.assertTrue(verified_discard['cold_result_verified'])
                self.assertTrue(verified_discard['discard_analysis_cache_verified'])
            for value in [None, 'false', '0', ['true', 'false'], ['true', 'true']]:
                with self.subTest(discard_analysis_cache=value):
                    invalid = measure({'discard_analysis_cache': value},
                                      client_command=discard_command, discard_analysis_cache=True)
                    self.assertFalse(invalid['cold_result_verified'])
                    self.assertFalse(invalid['discard_analysis_cache_verified'])
            for client in [command, command + ['--discard_analysis_cache=false'],
                           discard_command + ['--discard_analysis_cache=true'],
                           discard_command + ['--nodiscard_analysis_cache']]:
                with self.subTest(discard_client=client):
                    self.assertFalse(measure({'discard_analysis_cache': 'true'},
                                             client_command=client, discard_analysis_cache=True)['cold_result_verified'])
            jvm_command = command[:-1] + ['--host_jvm_args=-XX:ActiveProcessorCount=8', 'build']
            jvm_arguments = {'host_jvm_args': ['-Xmx8g', '-XX:ActiveProcessorCount=8']}
            verified_jvm = measure(jvm_arguments, client_command=jvm_command, jvm_processors=8)
            self.assertTrue(verified_jvm['cold_result_verified'])
            self.assertTrue(verified_jvm['jvm_processors_verified'])
            for values in [None, ['-Xmx8g'], ['-XX:ActiveProcessorCount=16'],
                           ['-XX:ActiveProcessorCount=8', '-XX:ActiveProcessorCount=16'],
                           ['-XX:ActiveProcessorCount=8', '-XX:ActiveProcessorCount=8']]:
                with self.subTest(jvm_arguments=values):
                    invalid = measure({'host_jvm_args': values}, client_command=jvm_command, jvm_processors=8)
                    self.assertFalse(invalid['cold_result_verified'])
                    self.assertFalse(invalid['jvm_processors_verified'])
            self.assertFalse(measure(jvm_arguments, jvm_processors=8)['cold_result_verified'])
            for value in [None, 'true', ['false', 'true']]:
                with self.subTest(sandbox_stashes=value):
                    invalid = measure({'experimental_inmemory_sandbox_stashes': value})
                    self.assertFalse(invalid['cold_result_verified'])
                    self.assertFalse(invalid['local_policy_verified'])
            for value in [None, 'false', ['true', 'false']]:
                with self.subTest(repository_hardlinks=value):
                    invalid = measure({'experimental_repository_cache_hardlinks': value}, repository_hardlinks=True)
                    self.assertFalse(invalid['cold_result_verified'])
                    self.assertFalse(invalid['repository_cache_hardlinks_verified'])
            valid = measure({'experimental_repository_cache_hardlinks': 'true'}, repository_hardlinks=True)
            self.assertTrue(valid['cold_result_verified'])
            self.assertTrue(valid['repository_cache_hardlinks_verified'])
            self.assertTrue(result['local_execution_verified'])
            longer_target = measure(elapsed=4000, target_seconds=5400)
            self.assertTrue(longer_target['cold_result_verified'])
            self.assertTrue(longer_target['under_target'])
            self.assertEqual(longer_target['target_seconds'], 5400)
            self.assertFalse(longer_target['under_one_hour'])
            self.assertFalse(measure(elapsed=4000)['under_target'])
            boundary = measure(elapsed=5400, target_seconds=5400)
            self.assertTrue(boundary['cold_result_verified'])
            self.assertFalse(boundary['under_target'])
            self.assertFalse(measure({'use_action_cache': 'true'}, target_seconds=5400)['under_target'])
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
            serialization = dict(base_bind_pch=True, eager_pchs=2,
                                 additional_pchs=('serialization_eager_pch',),
                                 pch_count=15, validator_count=15, prefix_count=1)
            self.assertTrue(measure({'define': 'CHROMIUM_BASE_BIND_PCH=1'}, **serialization)['cold_result_verified'])
            for suffixes in [('.raw.pch', '.pch'), ('.pch',)]:
                with self.subTest(missing_serialization=suffixes):
                    invalid = measure({'define': 'CHROMIUM_BASE_BIND_PCH=1'}, **serialization,
                                      mutate_pch_files=lambda folder: [
                                          (folder / ('serialization_eager_pch' + suffix)).unlink()
                                          for suffix in suffixes])
                    self.assertFalse(invalid['cold_result_verified'])
            invalid = measure({'define': 'CHROMIUM_BASE_BIND_PCH=1'}, **serialization,
                              mutate_pch_files=lambda folder: (folder / 'serialization_eager_pch.pch').write_bytes(b'changed'))
            self.assertFalse(invalid['cold_result_verified'])
            self.assertFalse(measure({'define': 'CHROMIUM_BASE_BIND_PCH=1'},
                                     **(serialization | {'validator_count': 14}))['cold_result_verified'])
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
