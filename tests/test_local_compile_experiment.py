import gzip
import json
from pathlib import Path
import tempfile
import unittest

from tools.ci.compile.local import local_compile_times, verify_ram_sandbox


class LocalCompileExperimentTest(unittest.TestCase):
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


if __name__ == '__main__':
    unittest.main()
