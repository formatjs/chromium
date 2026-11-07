import io
import gzip
from contextlib import redirect_stdout
import json
import os
from pathlib import Path
import struct
import tarfile
import tempfile
import unittest
from unittest import mock

from tools.ci.compression_benchmark import benchmark, tar_digest
from tools.ci import chromium as chromium_ci
from tools.ci.chromium import PLATFORMS, ROOT, binary_platform, build, checksum, cold_build_report, package, package_payload, stamp_payload, unpack, artifact_outputs


REVISION = '1' * 40


def elf(machine=62):
    header = bytearray(64)
    header[:6] = b'\x7fELF\x02\x01'
    struct.pack_into('<H', header, 18, machine)
    return header


class ArtifactsTest(unittest.TestCase):
    def test_cold_scratch_removes_abandoned_build_without_touching_other_files(self):
        scratch = chromium_ci.prepare_cold_scratch(self.root)
        abandoned = scratch / 'chromium-build-abandoned'
        abandoned.mkdir()
        (abandoned / 'large-output').write_bytes(b'old build')
        preserved = self.root / 'keep'
        preserved.write_bytes(b'not build state')
        self.assertEqual(chromium_ci.prepare_cold_scratch(self.root), scratch)
        self.assertFalse(abandoned.exists())
        self.assertEqual(preserved.read_bytes(), b'not build state')

    def test_cold_scratch_refuses_unowned_directory_or_symlink(self):
        for kind in ('unmarked', 'symlink', 'unexpected-file'):
            with self.subTest(kind=kind):
                parent = self.root / kind
                parent.mkdir()
                scratch = parent / '.chromium-cold-build'
                if kind == 'symlink':
                    scratch.symlink_to(self.bundle, target_is_directory=True)
                elif kind == 'unmarked':
                    scratch.mkdir()
                    (scratch / 'keep').write_bytes(b'not build state')
                else:
                    chromium_ci.prepare_cold_scratch(parent)
                    (scratch / 'keep').write_bytes(b'not build state')
                with self.assertRaisesRegex(ValueError, 'cold scratch'):
                    chromium_ci.prepare_cold_scratch(parent)
                self.assertTrue((self.bundle / 'chrome').exists())
                if kind != 'symlink':
                    self.assertEqual((scratch / 'keep').read_bytes(), b'not build state')

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.bundle = self.root / 'input'
        self.bundle.mkdir()
        (self.bundle / 'chrome').write_bytes(elf())
        (self.bundle / 'chrome').chmod(0o755)
        (self.bundle / 'resources.pak').write_bytes(b'locale data')
        self.target = PLATFORMS['linux-amd64']

    def archive(self):
        return package(self.bundle, self.root / 'artifacts', self.target, REVISION)

    def test_compression_benchmark_follows_runfiles_bundle_link(self):
        linked = self.root / 'runfiles-bundle'
        linked.symlink_to(self.bundle, target_is_directory=True)
        directory = self.root / 'compression-report'
        with redirect_stdout(io.StringIO()):
            benchmark(linked, self.target, directory)
        report = json.loads((directory / 'report.json').read_text())
        original = package_payload(self.bundle, self.root / 'original.tar.gz', self.target)
        self.assertTrue(report['tar_bytes_match'])
        self.assertTrue(report['repeated_gzip_bytes_match'])
        self.assertEqual([mode['compression_level'] for mode in report['modes']], [6, 1, 1, 6])
        self.assertTrue(all(mode['tar'] == tar_digest(original) for mode in report['modes']))

    def test_compression_levels_preserve_complete_tar_bytes(self):
        digests = []
        for level in (1, 6):
            payload = package_payload(self.bundle, self.root / f'level-{level}.tar.gz',
                                      self.target, compression_level=level)
            with gzip.open(payload, 'rb') as source:
                digests.append(source.read())
        self.assertEqual(digests[0], digests[1])

    def test_revision_stamping_reuses_compressed_payload_without_recompression(self):
        payload = package_payload(self.bundle, self.root / 'payload.tar.gz', self.target)
        original = payload.read_bytes()
        for revision in (REVISION, '2' * 40):
            archive = stamp_payload(payload, self.root / revision, self.target, revision)
            self.assertTrue(archive.read_bytes().endswith(original))
            relocated = unpack(archive, self.root / ('relocated-' + revision), self.target, revision)
            self.assertEqual((relocated / 'chrome').read_bytes(), elf())
            self.assertEqual((relocated / 'resources.pak').read_bytes(), b'locale data')
        self.assertEqual(payload.read_bytes(), original)

    def windows_archive(self):
        self.target = PLATFORMS['windows-amd64']
        binary = bytearray(128)
        binary[:2] = b'MZ'
        struct.pack_into('<I', binary, 60, 64)
        binary[64:68] = b'PE\0\0'
        struct.pack_into('<H', binary, 68, 0x8664)
        (self.bundle / 'chrome.exe').write_bytes(binary)
        return self.archive()

    def test_windows_extraction_grants_installer_capabilities_read_execute(self):
        archive = self.windows_archive()
        with mock.patch('tools.ci.chromium.platform.system', return_value='Windows'), \
                mock.patch('tools.ci.chromium.subprocess.run') as process:
            bundle = unpack(archive, self.root / 'relocated', self.target, REVISION)
        grants = set()
        for call in process.call_args_list:
            arguments = call.args[0]
            self.assertEqual(arguments[:2], ['icacls', str(bundle)])
            self.assertTrue(call.kwargs['check'])
            grants.update(value for value in arguments if value.startswith('*S-'))
        self.assertEqual(grants, {
            '*S-1-15-3-1024-3424233489-972189580-2057154623-747635277-1604371224-'
            '316187997-3786583170-1043257646:(OI)(CI)(RX)',
            '*S-1-15-3-1024-2302894289-466761758-1166120688-1039016420-2430351297-'
            '4240214049-4028510897-3317428798:(OI)(CI)(RX)',
        })

    def test_invalid_windows_provenance_cannot_change_permissions(self):
        archive = self.windows_archive()
        with mock.patch('tools.ci.chromium.platform.system', return_value='Windows'), \
                mock.patch('tools.ci.chromium.subprocess.run', side_effect=AssertionError('unverified ACL change')):
            with self.assertRaisesRegex(ValueError, 'provenance'):
                unpack(archive, self.root / 'relocated', self.target, '2' * 40)

    def test_round_trip_preserves_executable_and_resources(self):
        destination = unpack(self.archive(), self.root / 'relocated', self.target, REVISION)
        self.assertEqual((destination / 'resources.pak').read_bytes(), b'locale data')
        self.assertEqual(binary_platform(destination / 'chrome'), ('linux', 'amd64'))
        self.assertTrue(os.access(destination / 'chrome', os.X_OK))

    def test_wrong_architecture_cannot_be_packaged(self):
        with self.assertRaisesRegex(ValueError, 'Wrong artifact architecture'):
            package(self.bundle, self.root / 'artifacts', PLATFORMS['linux-arm64'], REVISION)

    def test_corruption_is_rejected_before_extraction(self):
        archive = self.archive()
        with archive.open('ab') as output:
            output.write(b'corrupted')
        with self.assertRaisesRegex(ValueError, 'SHA256 mismatch'):
            unpack(archive, self.root / 'relocated', self.target, REVISION)
        self.assertFalse((self.root / 'relocated').exists())

    def test_artifact_from_another_commit_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'provenance'):
            unpack(self.archive(), self.root / 'relocated', self.target, '2' * 40)

    def test_archive_cannot_escape_destination(self):
        archive = self.root / 'escape.tar.gz'
        with tarfile.open(archive, 'w:gz') as output:
            member = tarfile.TarInfo('../escaped')
            member.size = 4
            output.addfile(member, io.BytesIO(b'bad!'))
        archive.with_suffix('.gz.sha256').write_text(checksum(archive))
        with self.assertRaisesRegex(ValueError, 'Invalid artifact path'):
            unpack(archive, self.root / 'relocated', self.target, REVISION)
        self.assertFalse((self.root / 'escaped').exists())

    def test_windows_and_macos_headers(self):
        cases = []
        for machine, arch in [(0x8664, 'amd64'), (0xAA64, 'arm64')]:
            header = bytearray(134)
            header[:2] = b'MZ'
            struct.pack_into('<I', header, 60, 128)
            header[128:132] = b'PE\0\0'
            struct.pack_into('<H', header, 132, machine)
            cases.append((header, ('windows', arch)))
        header = bytearray(64)
        header[:4] = b'\xcf\xfa\xed\xfe'
        struct.pack_into('<I', header, 4, 0x100000C)
        cases.append((header, ('darwin', 'arm64')))
        cases.append((elf(183), ('linux', 'arm64')))
        for index, (header, expected) in enumerate(cases):
            with self.subTest(expected=expected):
                binary = self.root / f'binary-{index}'
                binary.write_bytes(header)
                self.assertEqual(binary_platform(binary), expected)

    def test_hosted_build_uses_one_invocation_and_cached_archive(self):
        source = self.archive()
        sidecar = source.with_suffix('.gz.sha256')
        label = '//tools/ci:linux-amd64_archive'

        def execute(command, **kwargs):
            self.assertEqual(command[:5], ['bazel', '--host_jvm_args=-Xmx12g', 'build',
                                          '--config=browser', '--config=buildbuddy'])
            self.assertIn('--noexperimental_remote_discard_merkle_trees', command)
            self.assertIn('--//tools/ci:revision=' + REVISION, command)
            self.assertEqual(command[-1], label)
            self.assertEqual(kwargs, {'cwd': ROOT, 'check': True})
            events = Path(next(value.split('=', 1)[1] for value in command
                               if value.startswith('--build_event_json_file=')))
            events.write_text('\n'.join(json.dumps(event) for event in [
                {'id': {'namedSet': {'id': 'artifacts'}}, 'namedSetOfFiles': {
                    'files': [{'uri': item.as_uri()} for item in [source, sidecar]]}},
                {'id': {'targetCompleted': {'label': label}}, 'completed': {
                    'success': True, 'outputGroup': [{'name': 'default', 'fileSets': [{'id': 'artifacts'}]}]}},
            ]))

        environment = {'BUILDBUDDY_CI_RUNNER_ABSPATH': '/runner/ci_runner'}
        with mock.patch.dict(os.environ, environment, clear=True), \
                mock.patch('tools.ci.chromium.subprocess.run', side_effect=execute) as process:
            archive = build(self.target, self.root / 'hosted-artifacts', REVISION, hosted=True)
        self.assertEqual(process.call_count, 1)
        destination = unpack(archive, self.root / 'hosted-output', self.target, REVISION)
        self.assertEqual((destination / 'resources.pak').read_bytes(), b'locale data')

    def test_hosted_macos_build_requests_sandboxed_link_and_bounded_downloads(self):
        environment = {'BUILDBUDDY_CI_RUNNER_ABSPATH': '/runner/ci_runner'}
        with mock.patch.dict(os.environ, environment, clear=True), \
                mock.patch('tools.ci.chromium.subprocess.run',
                           side_effect=RuntimeError('captured build command')) as process:
            with self.assertRaisesRegex(RuntimeError, 'captured build command'):
                build(PLATFORMS['darwin-arm64'], self.root / 'hosted-artifacts', REVISION, hosted=True)
        command = process.call_args.args[0]
        self.assertIn('--strategy=CppLink=sandboxed', command)
        self.assertIn('--remote_max_connections=8', command)
        self.assertEqual(command[-1], '//tools/ci:darwin-arm64_archive')

    def test_archive_bytes_ignore_input_mtime_and_non_executable_permissions(self):
        first = package(self.bundle, self.root / 'first', self.target, REVISION).read_bytes()
        for path in self.bundle.rglob('*'):
            os.utime(path, (1234567890, 1234567890))
        (self.bundle / 'resources.pak').chmod(0o600)
        second = package(self.bundle, self.root / 'second', self.target, REVISION).read_bytes()
        self.assertEqual(first, second)
        with tarfile.open(fileobj=io.BytesIO(second), mode='r:gz') as archive:
            self.assertTrue(all(item.mtime == item.uid == item.gid == 0 for item in archive))

    def test_archive_bytes_ignore_input_hardlink_layout(self):
        source = self.bundle / 'resources.pak'
        duplicate = self.bundle / 'resources-copy.pak'
        duplicate.write_bytes(source.read_bytes())
        copied = package(self.bundle, self.root / 'copied', self.target, REVISION).read_bytes()
        duplicate.unlink()
        duplicate.hardlink_to(source)
        linked = package(self.bundle, self.root / 'linked', self.target, REVISION).read_bytes()
        self.assertEqual(copied, linked)
        with tarfile.open(fileobj=io.BytesIO(linked), mode='r:gz') as archive:
            self.assertTrue(all(not item.islnk() for item in archive))

    def test_macos_framework_symlinks_survive_handoff(self):
        target = PLATFORMS['darwin-arm64']
        executable = self.bundle / target['executable']
        executable.parent.mkdir(parents=True)
        header = bytearray(64)
        header[:4] = b'\xcf\xfa\xed\xfe'
        struct.pack_into('<I', header, 4, 0x100000C)
        executable.write_bytes(header)
        framework = self.bundle / 'Chromium.app/Contents/Frameworks/Chromium Framework.framework'
        version = framework / 'Versions/142'
        version.mkdir(parents=True)
        (version / 'Chromium Framework').write_bytes(b'framework payload')
        (framework / 'Versions/Current').symlink_to('142')
        (framework / 'Chromium Framework').symlink_to('Versions/Current/Chromium Framework')
        archive = package(self.bundle, self.root / 'artifacts', target, REVISION)
        with tarfile.open(archive, 'r:gz') as contents:
            self.assertEqual(sum(member.issym() for member in contents), 2)
        relocated = unpack(archive, self.root / 'relocated', target, REVISION)
        installed = relocated / framework.relative_to(self.bundle)
        self.assertEqual(os.readlink(installed / 'Versions/Current'), '142')
        self.assertEqual((installed / 'Chromium Framework').read_bytes(), b'framework payload')

    def test_failed_or_remote_only_build_outputs_are_rejected(self):
        events = self.root / 'events.json'
        label = '//tools/ci:linux-amd64_archive'
        for success, uri in [(False, (self.root / 'archive').as_uri()), (True, 'bytestream://remote/archive')]:
            events.write_text('\n'.join(json.dumps(event) for event in [
                {'id': {'namedSet': {'id': 'files'}}, 'namedSetOfFiles': {'files': [{'uri': uri}]}},
                {'id': {'targetCompleted': {'label': label}}, 'completed': {
                    'success': success, 'outputGroup': [{'name': 'default', 'fileSets': [{'id': 'files'}]}]}},
            ]))
            with self.subTest(success=success), self.assertRaises(ValueError):
                artifact_outputs(events, label)

    def test_hosted_mode_requires_managed_runner(self):
        with mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch('tools.ci.chromium.subprocess.run') as execute:
            with self.assertRaisesRegex(ValueError, 'BuildBuddy workflow runner'):
                build(self.target, self.root / 'artifacts', REVISION, hosted=True)
        execute.assert_not_called()

    def test_cold_result_requires_success_real_compiles_and_no_cache_reuse(self):
        events = self.root / 'events.json'
        for success, local_hits, remote_hits, compiles, verified in [
            (True, 0, 0, 12345, True),
            (False, 0, 0, 12345, False),
            (True, 1, 0, 12345, False),
            (True, 0, 1, 12345, False),
            (True, 0, 0, 0, False),
        ]:
            with self.subTest(success=success, local_hits=local_hits, remote_hits=remote_hits, compiles=compiles):
                events.write_text(json.dumps({'structuredCommandLine': {
                    'commandLineLabel': 'canonical', 'sections': [{
                        'sectionLabel': 'startup options', 'optionList': {'option': [{
                            'optionName': 'output_base', 'optionValue': str(self.root / 'fresh-base'),
                        }]},
                    }],
                }}) + '\n' + json.dumps({'buildMetrics': {'actionSummary': {
                    'actionData': [{'mnemonic': 'CppCompile', 'actionsExecuted': str(compiles)}],
                    'actionCacheStatistics': {'hits': local_hits},
                    'runnerCount': [{'name': 'remote', 'count': compiles},
                                    {'name': 'remote cache hit', 'count': remote_hits}],
                }}}))
                result = cold_build_report(events, 9000, success,
                                           expected_output_base=self.root / 'fresh-base',
                                           output_base_was_fresh=True)
                self.assertEqual(result['cold_result_verified'], verified)
                self.assertEqual(result['elapsed_seconds'], 9000)
                self.assertEqual(result['cpp_compile_actions'], compiles)
        events.write_text('{"incomplete":')
        self.assertFalse(cold_build_report(events, 1, False)['cold_result_verified'])

    def test_cold_result_rejects_managed_rc_output_base(self):
        events = self.root / 'events.json'
        events.write_text('\n'.join(json.dumps(event) for event in [
            {'structuredCommandLine': {'commandLineLabel': 'canonical', 'sections': [{
                'sectionLabel': 'startup options', 'optionList': {'option': [
                    {'optionName': 'output_base', 'optionValue': '/home/buildbuddy/workspace/output-base'},
                    {'optionName': 'remote_header', 'optionValue': 'DO_NOT_EXPORT'},
                ]}}]}},
            {'buildMetrics': {'actionSummary': {
                'actionData': [{'mnemonic': 'CppCompile', 'actionsExecuted': '12345'}],
                'actionCacheStatistics': {'hits': 0},
                'runnerCount': [{'name': 'remote', 'count': 12345}],
            }}},
        ]))
        result = cold_build_report(events, 100, True)
        self.assertFalse(result['cold_result_verified'])
        self.assertNotIn('DO_NOT_EXPORT', json.dumps(result))
        result = cold_build_report(events, 100, True, expected_output_base=self.root / 'fresh-base',
                                   output_base_was_fresh=True)
        self.assertFalse(result['cold_result_verified'])
        self.assertEqual(result['cache_state']['bazel_output_state'], 'unverified')

    def test_cold_failure_keeps_measurement_without_reusing_bazel_state(self):
        directory = self.root / 'cold-artifacts'
        environment = {'BUILDBUDDY_CI_RUNNER_ABSPATH': '/runner/ci_runner'}
        roots = []

        def fail(command, **kwargs):
            root = Path(next(value.split('=', 1)[1] for value in command
                             if value.startswith('--output_user_root=')))
            self.assertFalse(root.exists())
            output_base = Path(next(value.split('=', 1)[1] for value in command
                                    if value.startswith('--output_base=')))
            self.assertFalse(output_base.exists())
            self.assertEqual(output_base, root.parent / 'output-base')
            roots.append(root)
            self.assertIn('--batch', command[:command.index('build')])
            self.assertIn('--remote_accept_cached=false', command)
            self.assertIn('--disk_cache=', command)
            self.assertIn('--repo_contents_cache=', command)
            self.assertIn('--modify_execution_info=.*=+no-cache', command)
            self.assertIn('--repository_cache=' + str(root.parent / 'repository-cache'), command)
            events = Path(next(value.split('=', 1)[1] for value in command
                               if value.startswith('--build_event_json_file=')))
            profile = Path(next(value.split('=', 1)[1] for value in command
                                if value.startswith('--profile=')))
            self.assertFalse(events.resolve().is_relative_to(directory.resolve()))
            self.assertEqual(profile.parent, directory)
            events.write_text(json.dumps({'started': {'uuid': 'cold-failure'}}) + '\n')
            profile.write_text('{"traceEvents":[')
            raise RuntimeError('build failed')

        with mock.patch.dict(os.environ, environment, clear=True), \
                mock.patch('tools.ci.chromium.ROOT', self.root / 'repo'), \
                mock.patch('tools.ci.chromium.subprocess.run', side_effect=fail):
            for _ in range(2):
                with self.assertRaisesRegex(RuntimeError, 'build failed'):
                    build(self.target, directory, REVISION, hosted=True, cold=True)
                report = json.loads((directory / 'cold-build.json').read_text())
                self.assertFalse(report['build_succeeded'])
                self.assertFalse(report['cold_result_verified'])
                self.assertEqual(report['invocation_id'], 'cold-failure')
                self.assertFalse((directory / 'cold-events.json').exists())
                self.assertTrue((directory / 'cold-profile.json').exists())
                self.assertEqual(report['cache_state']['execution_policy'], 'no-cache; no in-flight action merging')
                for phase in ('before', 'after'):
                    filesystem = report['client_filesystem'][phase]
                    self.assertGreater(filesystem['total_bytes'], 0)
                    self.assertGreaterEqual(filesystem['free_bytes'], 0)
                    self.assertLessEqual(filesystem['free_bytes'], filesystem['total_bytes'])
        self.assertNotEqual(roots[0], roots[1])
if __name__ == '__main__':
    unittest.main()
