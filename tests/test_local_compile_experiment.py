import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from tools.ci.compile.experiment import archive_outputs
from tools.ci.compile.local import _profile_events, local_compile_times, verify_ram_sandbox


class LocalCompileExperimentTest(unittest.TestCase):
    def test_archive_reader_selects_requested_output_group(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            events = []
            for group, content in [('default', b'default'), ('archive', b'archive')]:
                file = root / (group + '.a')
                file.write_bytes(content)
                events.append({'id': {'namedSet': {'id': group}},
                               'namedSetOfFiles': {'files': [{'uri': file.as_uri()}]}})
            events.append({'id': {'targetCompleted': {'label': '//:cohort'}},
                           'completed': {'success': True, 'outputGroup': [
                               {'name': group, 'fileSets': [{'id': group}]}
                               for group in ['default', 'archive']]}})
            path = root / 'events.json'
            path.write_text('\n'.join(json.dumps(event) for event in events))
            for group in ['default', 'archive']:
                files, _ = archive_outputs(path, '//:cohort', output_group=group)
                self.assertEqual(files, {group + '.a': hashlib.sha256(group.encode()).hexdigest()})
            with self.assertRaisesRegex(ValueError, 'did not produce an archive'):
                archive_outputs(path, '//:cohort', output_group='missing')

    def test_ram_comparison_requires_empty_dedicated_tmpfs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sandbox = root / 'sandbox'
            sandbox.mkdir()
            mountinfo = root / 'mountinfo'
            for filesystem in ('ext4', 'overlay', 'tmpfs'):
                mountinfo.write_text(f'1 0 0:1 / {sandbox} rw - {filesystem} source rw\n')
                if filesystem == 'tmpfs':
                    self.assertEqual(verify_ram_sandbox(sandbox, mountinfo), sandbox)
                else:
                    with self.assertRaisesRegex(ValueError, 'dedicated tmpfs'):
                        verify_ram_sandbox(sandbox, mountinfo)
            (sandbox / 'retained-state').touch()
            with self.assertRaisesRegex(ValueError, 'start empty'):
                verify_ram_sandbox(sandbox, mountinfo)

    def measure(self, events):
        with tempfile.TemporaryDirectory() as temporary:
            profile = Path(temporary) / 'profile.gz'
            with gzip.open(profile, 'wt') as stream:
                json.dump({'traceEvents': events}, stream)
            return local_compile_times(profile, ('src/sample.cc',))

    def test_local_timing_belongs_to_selected_compiler(self):
        action = {'ph': 'X', 'cat': 'action processing', 'name': 'Compiling src/sample.cc',
                  'args': {'mnemonic': 'CppCompile'}, 'tid': 1, 'ts': 1000000, 'dur': 1000000}
        child = {'ph': 'X', 'cat': 'general information', 'name': 'subprocess.run',
                 'tid': 1, 'ts': 1200000, 'dur': 500000}
        sandbox = {**child, 'name': 'sandbox.createFileSystem', 'ts': 1000000, 'dur': 100000}
        unrelated = [{**child, 'tid': 2}, {**child, 'ts': 3000000}]
        self.assertEqual(self.measure([action, child, sandbox, *unrelated]), {
            'src/sample.cc': {'action_seconds': 1.0, 'subprocess_seconds': .5,
                              'sandbox_creation_seconds': .1},
        })
        for events in ([action], [action, *unrelated], [action, action, child]):
            with self.subTest(events=events), self.assertRaises(ValueError):
                self.measure(events)

    def test_same_basename_and_unsorted_thread_events_stay_separate(self):
        action = {'ph': 'X', 'cat': 'action processing', 'name': 'Compiling a/sample.cc [for tool]',
                  'args': {'mnemonic': 'CppCompile'}, 'tid': 1, 'ts': 1000000, 'dur': 1000000}
        second = {**action, 'name': 'Compiling b/sample.cc', 'ts': 3000000}
        child = {'ph': 'X', 'name': 'subprocess.run', 'tid': 1, 'ts': 1200000, 'dur': 500000}
        other = {**child, 'ts': 3200000, 'dur': 250000}
        crossing = {**child, 'ts': 1900000, 'dur': 200000}
        with tempfile.TemporaryDirectory() as temporary:
            profile = Path(temporary) / 'profile.gz'
            with gzip.open(profile, 'wt') as stream:
                json.dump({'traceEvents': [other, second, crossing, child, action]}, stream)
            result = local_compile_times(profile, ('a/sample.cc', 'b/sample.cc'))
            with self.assertRaises(ValueError):
                local_compile_times(profile, ('sample.cc',))
        self.assertEqual(result['a/sample.cc']['subprocess_seconds'], .5)
        self.assertEqual(result['b/sample.cc']['subprocess_seconds'], .25)

    def test_streamed_profile_crosses_chunks_and_rejects_incomplete_json(self):
        event = {'name': 'large detail', 'args': {'detail': 'x' * 70000}}
        text = json.dumps({'otherData': {'id': 'build'}, 'traceEvents': [event]})
        with tempfile.TemporaryDirectory() as temporary:
            profile = Path(temporary) / 'profile.gz'
            with gzip.open(profile, 'wt') as stream:
                stream.write(text)
            self.assertEqual(list(_profile_events(profile)), [event])
            for broken in [text[:-1], text[:-4], text.replace(']}', ',]}')]:
                with gzip.open(profile, 'wt') as stream:
                    stream.write(broken)
                with self.subTest(tail=broken[-10:]), self.assertRaises(ValueError):
                    list(_profile_events(profile))


if __name__ == '__main__':
    unittest.main()
